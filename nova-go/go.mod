module nova-pc/nova-go

go 1.26.3

// The forks below are shared with Nova Android on purpose: one MASQUE/WARP code base, two apps.
// Paths are relative to this directory: <repo>/nova-go -> ../../Nova Android.
replace github.com/Diniboy1123/connect-ip-go => "../../Nova Android/tools/connect-ip-go"

replace github.com/Diniboy1123/usque => "../../Nova Android/build/deps/usque"

replace github.com/bepass-org/warp-plus => "../../Nova Android/tools/warp-plus"

// gvisor.patch deletes pkg/sync/runtime_constants_go125.go, required with Go 1.26.
replace gvisor.dev/gvisor => "../../Nova Android/build/deps/gvisor"

require (
	github.com/Diniboy1123/connect-ip-go v0.0.0-20260613064811-66cba32d7d33
	github.com/Diniboy1123/usque v0.0.0-00010101000000-000000000000
	github.com/bepass-org/warp-plus v0.0.0-00010101000000-000000000000
	github.com/flynn/noise v1.1.0
	github.com/quic-go/quic-go v0.65.0
	github.com/refraction-networking/utls v1.8.2
	github.com/things-go/go-socks5 v0.1.4
	github.com/yosida95/uritemplate/v3 v3.0.2
	golang.org/x/crypto v0.58.0
	golang.org/x/net v0.62.0
	golang.org/x/sys v0.49.0
	golang.zx2c4.com/wireguard v0.0.0-20260522210424-ecfc5a8d5446
)

require (
	github.com/andybalholm/brotli v1.1.1 // indirect
	github.com/avast/retry-go v3.0.0+incompatible // indirect
	github.com/dunglas/httpsfv v1.1.0 // indirect
	github.com/google/btree v1.1.3 // indirect
	github.com/klauspost/compress v1.18.0 // indirect
	github.com/noql-net/certpool v0.0.0-20250417123926-688b52c002ee // indirect
	github.com/patrickmn/go-cache v2.1.0+incompatible // indirect
	github.com/quic-go/qpack v0.6.0 // indirect
	github.com/songgao/water v0.0.0-20200317203138-2b4b6d7c09d8 // indirect
	github.com/txthinking/runnergroup v0.0.0-20250224021307-5864ffeb65ae // indirect
	github.com/txthinking/socks5 v0.0.0-20260601051520-339b044ab0eb // indirect
	golang.org/x/text v0.43.0 // indirect
	golang.org/x/time v0.15.0 // indirect
	golang.zx2c4.com/wintun v0.0.0-20230126152724-0fa3db229ce2 // indirect
	gvisor.dev/gvisor v0.0.0-20260616165937-8e4bc62602eb // indirect
)
