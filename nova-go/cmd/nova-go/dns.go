// Command registration for the DNS group: a loopback DNS listener that speaks DoH upstream.
package main

import "nova-pc/nova-go/dnsdoh"

func init() {
	register(group{
		name: "dns",
		help: "DNS over HTTPS: doh --listen 127.0.0.1:53 --upstream URL",
		run: func(args []string) int {
			return dnsdoh.Main(args)
		},
	})
}
