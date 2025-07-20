import unittest

from options_global import parse_global_options


class GlobalOptionsTest(unittest.TestCase):
    def test_parse_transport_default(self):
        options = parse_global_options('')
        self.assertEqual(options.enable_udp, True)
        self.assertEqual(options.enable_tcp, True)
        self.assertEqual(options.enable_tls, False)
        self.assertEqual(options.stun_server, None)

    def test_parse_transport_udp_enabled(self):
        options = parse_global_options('--udp enabled')
        self.assertEqual(options.enable_udp, True)

    def test_parse_transport_udp_disabled(self):
        options = parse_global_options('--udp=disabled')
        self.assertEqual(options.enable_udp, False)

    def test_parse_transport_tcp_enabled(self):
        options = parse_global_options('--tcp=enabled')
        self.assertEqual(options.enable_tcp, True)

    def test_parse_transport_tcp_disabled(self):
        options = parse_global_options('--tcp disabled')
        self.assertEqual(options.enable_tcp, False)

    def test_parse_transport_tls_enabled(self):
        options = parse_global_options('--tls=enabled')
        self.assertEqual(options.enable_tls, True)

    def test_parse_transport_tls_disabled(self):
        options = parse_global_options('--tls=disabled')
        self.assertEqual(options.enable_tls, False)

    def test_parse_stun_server(self):
        options = parse_global_options('--stun-server stun.example.com')
        self.assertEqual(options.stun_server, 'stun.example.com')
