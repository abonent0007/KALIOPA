// Package dnsdoh is a small DNS-over-HTTPS proxy: a loopback DNS listener that forwards
// every query to an HTTP/2 DoH endpoint.
//
// Why it exists: dns-ai.ru has no plain UDP/53 service, and the Windows build on the owner's
// machine has no DoH client of its own (Get-DnsClientDohServerAddress is absent). NRPT rules can
// only name an IP address, so Nova needs a local resolver that speaks DNS on 127.0.0.1 and DoH
// upstream. Go's net/http negotiates HTTP/2 on its own, which the endpoint requires (it answers
// HTTP/1.1 with 505).
//
// Only names Nova routes into the NRPT rule reach this listener; the process listens on loopback
// and never accepts remote connections.
package dnsdoh

import (
	"bytes"
	"context"
	"encoding/binary"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"golang.org/x/net/proxy"

	"nova-pc/nova-go/internal/parentwatch"
)

const (
	exitOK       = 0
	exitUsage    = 2
	exitInternal = 1

	defaultTimeout = 5 * time.Second
	defaultCache   = 60 * time.Second
	maxInflight    = 64
)

type config struct {
	listen    string
	upstream  string
	fallback  string
	proxyURL  string
	timeout   time.Duration
	cacheTTL  time.Duration
	parentPID int
	verbose   bool
}

func Main(args []string) int {
	if len(args) == 0 || args[0] != "doh" {
		fmt.Fprintln(os.Stderr, "usage: nova-go dns doh --listen 127.0.0.1:53 --upstream https://host/dns-query")
		return exitUsage
	}
	cfg, err := parseDoh(args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, "nova-go dns doh:", err)
		return exitUsage
	}
	return run(cfg)
}

func parseDoh(args []string) (config, error) {
	fs := flag.NewFlagSet("doh", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	cfg := config{}
	fs.StringVar(&cfg.listen, "listen", "127.0.0.1:53", "loopback address to serve DNS on")
	fs.StringVar(&cfg.upstream, "upstream", "", "DoH endpoint URL")
	fs.StringVar(&cfg.fallback, "fallback", "", "UDP DNS server for upstream failures, host:port")
	fs.StringVar(&cfg.proxyURL, "proxy", "", "http:// or socks5:// proxy for upstream requests")
	fs.DurationVar(&cfg.timeout, "timeout", defaultTimeout, "per-query upstream timeout")
	fs.DurationVar(&cfg.cacheTTL, "cache", defaultCache, "how long an answer is reused (0 disables)")
	fs.IntVar(&cfg.parentPID, "parent-pid", 0, "exit when this process exits")
	fs.BoolVar(&cfg.verbose, "verbose", false, "log every query")
	if err := fs.Parse(args); err != nil {
		return cfg, err
	}
	if cfg.upstream == "" {
		return cfg, errors.New("--upstream is required")
	}
	if !strings.HasPrefix(cfg.upstream, "https://") {
		return cfg, errors.New("--upstream must be an https:// URL")
	}
	if cfg.listen == "" {
		return cfg, errors.New("--listen is empty")
	}
	return cfg, nil
}

type server struct {
	cfg    config
	client *http.Client
	log    func(format string, args ...any)

	mu    sync.Mutex
	cache map[string]cacheEntry

	sem chan struct{}
}

type cacheEntry struct {
	msg     []byte
	expires time.Time
}

func run(cfg config) int {
	log := func(format string, args ...any) {
		fmt.Fprintf(os.Stderr, "%s %s\n", time.Now().Format("15:04:05"), fmt.Sprintf(format, args...))
	}
	transport := &http.Transport{
		ForceAttemptHTTP2:   true,
		MaxIdleConns:        8,
		IdleConnTimeout:     90 * time.Second,
		TLSHandshakeTimeout: cfg.timeout,
	}
	if err := applyProxy(transport, cfg.proxyURL); err != nil {
		log("proxy: %v", err)
		return exitUsage
	}
	srv := &server{
		cfg:    cfg,
		client: &http.Client{Timeout: cfg.timeout, Transport: transport},
		log:    log,
		cache:  make(map[string]cacheEntry),
		sem:    make(chan struct{}, maxInflight),
	}

	udpAddr, err := net.ResolveUDPAddr("udp", cfg.listen)
	if err != nil {
		log("resolve listen address: %v", err)
		return exitUsage
	}
	udpConn, err := net.ListenUDP("udp", udpAddr)
	if err != nil {
		log("listen udp %s: %v", cfg.listen, err)
		return exitInternal
	}
	defer udpConn.Close()

	var tcpLn net.Listener
	if tcpAddr, err := net.ResolveTCPAddr("tcp", cfg.listen); err == nil {
		tcpLn, err = net.ListenTCP("tcp", tcpAddr)
		if err == nil {
			defer tcpLn.Close()
		}
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	installSignals(cancel)
	if cfg.parentPID > 0 {
		done, err := parentwatch.Watch(cfg.parentPID)
		switch {
		case errors.Is(err, parentwatch.ErrGone):
			log("parent process is already gone")
			return exitOK
		case err != nil:
			log("cannot watch parent %d: %v", cfg.parentPID, err)
			return exitInternal
		default:
			go func() {
				select {
				case <-done:
					log("parent process exited")
					cancel()
				case <-ctx.Done():
				}
			}()
		}
	}

	log("listening on %s, upstream %s", cfg.listen, cfg.upstream)
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		srv.serveUDP(ctx, udpConn)
	}()
	if tcpLn != nil {
		wg.Add(1)
		go func() {
			defer wg.Done()
			srv.serveTCP(ctx, tcpLn)
		}()
	}
	<-ctx.Done()
	udpConn.Close()
	if tcpLn != nil {
		tcpLn.Close()
	}
	wg.Wait()
	return exitOK
}

// applyProxy routes DoH requests through a local proxy: an HTTP CONNECT proxy (Nova's secondary
// slot, 127.0.0.1:1371) or a SOCKS5 one (the WARP slot, 127.0.0.1:1370). Direct access to the
// endpoint is reset by the DPI in Russia, so the helper is normally started with one of them.
func applyProxy(transport *http.Transport, raw string) error {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	u, err := url.Parse(raw)
	if err != nil {
		return err
	}
	switch strings.ToLower(u.Scheme) {
	case "http", "https":
		transport.Proxy = http.ProxyURL(u)
		return nil
	case "socks5", "socks5h":
		dialer, err := proxy.SOCKS5("tcp", u.Host, nil, proxy.Direct)
		if err != nil {
			return err
		}
		transport.DialContext = func(ctx context.Context, network, addr string) (net.Conn, error) {
			if cd, ok := dialer.(proxy.ContextDialer); ok {
				return cd.DialContext(ctx, network, addr)
			}
			return dialer.Dial(network, addr)
		}
		return nil
	}
	return fmt.Errorf("unsupported proxy scheme %q", u.Scheme)
}

func installSignals(cancel context.CancelFunc) {
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-sig
		cancel()
	}()
}

func (s *server) serveUDP(ctx context.Context, conn *net.UDPConn) {
	buf := make([]byte, 4096)
	for {
		n, addr, err := conn.ReadFromUDP(buf)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			s.log("udp read: %v", err)
			continue
		}
		if n < 12 {
			continue
		}
		query := append([]byte(nil), buf[:n]...)
		go func() {
			resp := s.answer(ctx, query)
			if resp == nil {
				return
			}
			if _, err := conn.WriteToUDP(resp, addr); err != nil && ctx.Err() == nil {
				s.log("udp write: %v", err)
			}
		}()
	}
}

func (s *server) serveTCP(ctx context.Context, ln net.Listener) {
	for {
		conn, err := ln.Accept()
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			continue
		}
		go s.handleTCPConn(ctx, conn)
	}
}

func (s *server) handleTCPConn(ctx context.Context, conn net.Conn) {
	defer conn.Close()
	conn.SetDeadline(time.Now().Add(30 * time.Second))
	for {
		var sizeBuf [2]byte
		if _, err := io.ReadFull(conn, sizeBuf[:]); err != nil {
			return
		}
		size := int(binary.BigEndian.Uint16(sizeBuf[:]))
		if size < 12 || size > 65535 {
			return
		}
		query := make([]byte, size)
		if _, err := io.ReadFull(conn, query); err != nil {
			return
		}
		resp := s.answer(ctx, query)
		if resp == nil {
			return
		}
		if len(resp) > 65535 {
			return
		}
		binary.BigEndian.PutUint16(sizeBuf[:], uint16(len(resp)))
		if _, err := conn.Write(sizeBuf[:]); err != nil {
			return
		}
		if _, err := conn.Write(resp); err != nil {
			return
		}
	}
}

func (s *server) answer(ctx context.Context, query []byte) []byte {
	key, ok := cacheKey(query)
	if ok && s.cfg.cacheTTL > 0 {
		s.mu.Lock()
		entry, hit := s.cache[key]
		s.mu.Unlock()
		if hit && time.Now().Before(entry.expires) {
			return rewriteID(entry.msg, query)
		}
	}
	select {
	case s.sem <- struct{}{}:
		defer func() { <-s.sem }()
	case <-ctx.Done():
		return nil
	}
	resp, err := s.upstream(ctx, query)
	if err != nil {
		s.log("upstream failed: %v", err)
		if fb := s.fallbackAnswer(query); fb != nil {
			return fb
		}
		return servfail(query)
	}
	if ok && s.cfg.cacheTTL > 0 {
		s.mu.Lock()
		s.cache[key] = cacheEntry{msg: append([]byte(nil), resp...),
			expires: time.Now().Add(s.cfg.cacheTTL)}
		if len(s.cache) > 4096 {
			for k, v := range s.cache {
				if time.Now().After(v.expires) {
					delete(s.cache, k)
				}
			}
		}
		s.mu.Unlock()
	}
	return rewriteID(resp, query)
}

func (s *server) upstream(ctx context.Context, query []byte) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.cfg.upstream, bytes.NewReader(query))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/dns-message")
	req.Header.Set("Accept", "application/dns-message")
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("status %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 65535))
	if err != nil {
		return nil, err
	}
	if len(body) < 12 {
		return nil, errors.New("short DoH response")
	}
	return body, nil
}

func (s *server) fallbackAnswer(query []byte) []byte {
	if s.cfg.fallback == "" {
		return nil
	}
	conn, err := net.DialTimeout("udp", s.cfg.fallback, s.cfg.timeout)
	if err != nil {
		return nil
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(s.cfg.timeout))
	if _, err := conn.Write(query); err != nil {
		return nil
	}
	buf := make([]byte, 4096)
	n, err := conn.Read(buf)
	if err != nil || n < 12 {
		return nil
	}
	return append([]byte(nil), buf[:n]...)
}

// cacheKey builds "name|type" from the question. Multiple questions and malformed packets are
// not cached (ok=false) but still answered.
func cacheKey(query []byte) (string, bool) {
	if len(query) < 12 {
		return "", false
	}
	qd := binary.BigEndian.Uint16(query[4:6])
	if qd != 1 {
		return "", false
	}
	offset := 12
	var name strings.Builder
	for offset < len(query) {
		length := int(query[offset])
		offset++
		if length == 0 {
			break
		}
		if length&0xC0 != 0 || offset+length > len(query) {
			return "", false
		}
		if name.Len() > 0 {
			name.WriteByte('.')
		}
		name.Write(query[offset : offset+length])
		offset += length
	}
	if offset+4 > len(query) {
		return "", false
	}
	qtype := binary.BigEndian.Uint16(query[offset : offset+2])
	return fmt.Sprintf("%s|%d", strings.ToLower(name.String()), qtype), true
}

func rewriteID(resp, query []byte) []byte {
	if len(resp) < 2 || len(query) < 2 {
		return resp
	}
	if resp[0] == query[0] && resp[1] == query[1] {
		return resp
	}
	out := append([]byte(nil), resp...)
	out[0], out[1] = query[0], query[1]
	return out
}

// servfail builds a minimal SERVFAIL answer carrying the original question, so the client fails
// fast instead of waiting for its own timeout.
func servfail(query []byte) []byte {
	if len(query) < 12 {
		return nil
	}
	resp := append([]byte(nil), query...)
	flags := binary.BigEndian.Uint16(resp[2:4])
	flags = (flags & 0x0100) | 0x8000 | 0x0080 | 0x0002 // keep RD, set QR/RA, rcode SERVFAIL
	binary.BigEndian.PutUint16(resp[2:4], flags)
	binary.BigEndian.PutUint16(resp[6:8], 0) // ANCOUNT
	binary.BigEndian.PutUint16(resp[8:10], 0)
	binary.BigEndian.PutUint16(resp[10:12], 0)
	return resp
}
