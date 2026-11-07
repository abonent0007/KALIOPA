package dnsdoh

import (
	"encoding/binary"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

// buildQuery is a minimal A-record query for tests.
func buildQuery(name string, qtype uint16, qid uint16) []byte {
	out := make([]byte, 12)
	binary.BigEndian.PutUint16(out[0:2], qid)
	binary.BigEndian.PutUint16(out[2:4], 0x0100)
	binary.BigEndian.PutUint16(out[4:6], 1)
	for _, part := range splitLabels(name) {
		out = append(out, byte(len(part)))
		out = append(out, part...)
	}
	out = append(out, 0)
	var tail [4]byte
	binary.BigEndian.PutUint16(tail[0:2], qtype)
	binary.BigEndian.PutUint16(tail[2:4], 1)
	return append(out, tail[:]...)
}

func splitLabels(name string) [][]byte {
	var parts [][]byte
	start := 0
	for i := 0; i <= len(name); i++ {
		if i == len(name) || name[i] == '.' {
			if i > start {
				parts = append(parts, []byte(name[start:i]))
			}
			start = i + 1
		}
	}
	return parts
}

// answerA builds a response with one A record and the given id.
func answerA(query []byte, qid uint16, ip [4]byte) []byte {
	resp := append([]byte(nil), query...)
	binary.BigEndian.PutUint16(resp[0:2], qid)
	binary.BigEndian.PutUint16(resp[2:4], 0x8180)
	binary.BigEndian.PutUint16(resp[6:8], 1)
	// Question is already in the query; append an answer pointing at it.
	resp = append(resp, 0xC0, 0x0C) // name pointer to offset 12
	var rr [10]byte
	binary.BigEndian.PutUint16(rr[0:2], 1)  // TYPE A
	binary.BigEndian.PutUint16(rr[2:4], 1)  // CLASS IN
	binary.BigEndian.PutUint32(rr[4:8], 60) // TTL
	binary.BigEndian.PutUint16(rr[8:10], 4)
	resp = append(resp, rr[:]...)
	return append(resp, ip[:]...)
}

func TestCacheKey(t *testing.T) {
	query := buildQuery("ChatGPT.com", 1, 0x1111)
	key, ok := cacheKey(query)
	if !ok || key != "chatgpt.com|1" {
		t.Fatalf("cacheKey = %q, %v", key, ok)
	}
	if _, ok := cacheKey([]byte{1, 2, 3}); ok {
		t.Fatal("short packet must not be cacheable")
	}
	multi := append([]byte(nil), query...)
	binary.BigEndian.PutUint16(multi[4:6], 2)
	if _, ok := cacheKey(multi); ok {
		t.Fatal("multi-question packet must not be cacheable")
	}
}

func TestServfailKeepsQuestion(t *testing.T) {
	query := buildQuery("example.com", 1, 0x2222)
	resp := servfail(query)
	if len(resp) != len(query) {
		t.Fatalf("servfail length %d, want %d", len(resp), len(query))
	}
	if rcode := binary.BigEndian.Uint16(resp[2:4]) & 0x000F; rcode != 2 {
		t.Fatalf("rcode = %d, want SERVFAIL", rcode)
	}
	if binary.BigEndian.Uint16(resp[6:8]) != 0 {
		t.Fatal("ANCOUNT must be zero")
	}
	if binary.BigEndian.Uint16(resp[0:2]) != 0x2222 {
		t.Fatal("id must be preserved")
	}
}

func TestRewriteID(t *testing.T) {
	resp := []byte{0xAA, 0xBB, 0, 0}
	out := rewriteID(resp, []byte{0x12, 0x34})
	if out[0] != 0x12 || out[1] != 0x34 {
		t.Fatalf("id not rewritten: %x", out[:2])
	}
	if resp[0] != 0xAA {
		t.Fatal("input must not be mutated")
	}
}

func TestAnswerUsesDoHAndRewritesID(t *testing.T) {
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if got := r.Header.Get("Content-Type"); got != "application/dns-message" {
			t.Errorf("content-type = %q", got)
		}
		body, _ := io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/dns-message")
		w.Write(answerA(body, 0x4242, [4]byte{62, 60, 230, 61}))
	}))
	defer srv.Close()

	s := &server{
		cfg:    config{upstream: srv.URL, timeout: 2 * time.Second, cacheTTL: time.Minute},
		client: srv.Client(),
		log:    t.Logf,
		cache:  map[string]cacheEntry{},
		sem:    make(chan struct{}, 2),
	}
	query := buildQuery("chatgpt.com", 1, 0x0101)
	resp := s.answer(t.Context(), query)
	if resp == nil || len(resp) < 12 {
		t.Fatal("no response")
	}
	if binary.BigEndian.Uint16(resp[0:2]) != 0x0101 {
		t.Fatal("response id must match the query")
	}
	if calls.Load() != 1 {
		t.Fatalf("upstream calls = %d, want 1", calls.Load())
	}

	// Second identical query is served from the cache.
	resp2 := s.answer(t.Context(), query)
	if resp2 == nil || calls.Load() != 1 {
		t.Fatalf("cache miss: calls = %d", calls.Load())
	}
	if binary.BigEndian.Uint16(resp2[0:2]) != 0x0101 {
		t.Fatal("cached response id must match the query")
	}
}

func TestUpstreamFailureFallsBackToServfail(t *testing.T) {
	s := &server{
		cfg:    config{upstream: "https://127.0.0.1:1/dns-query", timeout: 300 * time.Millisecond},
		client: &http.Client{Timeout: 300 * time.Millisecond},
		log:    t.Logf,
		cache:  map[string]cacheEntry{},
		sem:    make(chan struct{}, 1),
	}
	resp := s.answer(t.Context(), buildQuery("example.com", 1, 0x0303))
	if resp == nil {
		t.Fatal("expected SERVFAIL, got nil")
	}
	if rcode := binary.BigEndian.Uint16(resp[2:4]) & 0x000F; rcode != 2 {
		t.Fatalf("rcode = %d, want SERVFAIL", rcode)
	}
}
