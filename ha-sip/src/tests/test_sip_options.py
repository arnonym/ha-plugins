import unittest

from pjsua2 import PJ_TURN_TP_UDP, PJ_TURN_TP_TCP, PJ_TURN_TP_TLS

from options_sip import parse_sip_options


class SipOptionsTest(unittest.TestCase):
    def test_parse_without_options(self):
        options = parse_sip_options('')
        self.assertEqual(options.proxy, None)
        self.assertEqual(options.enable_ice, True)
        self.assertEqual(options.turn_server, None)
        self.assertEqual(options.sip_stun_use, True)
        self.assertEqual(options.media_stun_use, True)
        self.assertEqual(options.contact_rewrite_use, True)
        self.assertEqual(options.via_rewrite_use, True)
        self.assertEqual(options.sdp_nat_rewrite_use, True)
        self.assertEqual(options.sip_outbound_use, True)

    def test_parse_proxy(self):
        options = parse_sip_options('--proxy sip:example.com')
        self.assertEqual(options.proxy, 'sip:example.com')

    def test_parse_ice_disabled(self):
        options = parse_sip_options('--ice disabled')
        self.assertEqual(options.enable_ice, False)

    def test_parse_ice_enabled(self):
        options = parse_sip_options('--ice enabled')
        self.assertEqual(options.enable_ice, True)

    def test_parse_sip_stun_use(self):
        options = parse_sip_options('--use-stun-for-sip disabled')
        self.assertEqual(options.sip_stun_use, False)

    def test_parse_media_stun_use(self):
        options = parse_sip_options('--use-stun-for-media disabled')
        self.assertEqual(options.media_stun_use, False)

    def test_parse_use_contact_rewrite(self):
        options = parse_sip_options('--use-contact-rewrite disabled')
        self.assertEqual(options.contact_rewrite_use, False)

    def test_parse_use_via_rewrite(self):
        options = parse_sip_options('--use-via-rewrite disabled')
        self.assertEqual(options.via_rewrite_use, False)

    def test_parse_use_sdp_nat_rewrite(self):
        options = parse_sip_options('--use-sdp-nat-rewrite disabled')
        self.assertEqual(options.sdp_nat_rewrite_use, False)

    def test_parse_use_sip_outbound(self):
        options = parse_sip_options('--use-sip-outbound disabled')
        self.assertEqual(options.sip_outbound_use, False)

    def test_parse_turn_server(self):
        options = parse_sip_options('--turn-server turn:example.com:3478 --turn-connection-type udp --turn-user user --turn-password pass')
        if not options.turn_server:
            self.fail('Turn server not set')
        self.assertEqual(options.turn_server.server, 'turn:example.com:3478')
        self.assertEqual(options.turn_server.connection_type, PJ_TURN_TP_UDP)
        self.assertEqual(options.turn_server.user, 'user' )
        self.assertEqual(options.turn_server.password, 'pass')

    def test_parse_turn_server_type_tcp(self):
        options = parse_sip_options('--turn-server turn:example.com:3478 --turn-connection-type tcp --turn-user user --turn-password pass')
        if not options.turn_server:
            self.fail('Turn server not set')
        self.assertEqual(options.turn_server.connection_type, PJ_TURN_TP_TCP)

    def test_parse_turn_server_type_tls(self):
        options = parse_sip_options('--turn-server turn:example.com:3478 --turn-connection-type tls --turn-user user --turn-password pass')
        if not options.turn_server:
            self.fail('Turn server not set')
        self.assertEqual(options.turn_server.connection_type, PJ_TURN_TP_TLS)

    def test_parse_extract_headers_default(self):
        options = parse_sip_options('')
        self.assertEqual(options.extract_headers, [])

    def test_parse_extract_headers_single(self):
        options = parse_sip_options('--extract-headers X-Custom-Header')
        self.assertEqual(options.extract_headers, ['X-Custom-Header'])

    def test_parse_extract_headers_multiple(self):
        options = parse_sip_options('--extract-headers X-Custom-Header,P-Asserted-Identity,X-Another')
        self.assertEqual(options.extract_headers, ['X-Custom-Header', 'P-Asserted-Identity', 'X-Another'])

