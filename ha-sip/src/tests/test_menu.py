import unittest
from menu import normalize_menu, pretty_print_menu, MenuFromStdin
from constants import DEFAULT_RING_TIMEOUT


def make_menu(**overrides) -> MenuFromStdin:
    base: MenuFromStdin = {
        'id': None,
        'message': None,
        'handle_as_template': None,
        'audio_file': None,
        'language': None,
        'action': None,
        'choices_are_pin': None,
        'post_action': None,
        'timeout': None,
        'choices': None,
        'cache_audio': None,
        'wait_for_audio_to_finish': None,
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


class NormalizeMenuNoneTest(unittest.TestCase):
    def test_none_input_returns_none_and_empty_map(self):
        menu, menu_map = normalize_menu(None, 'en', 0)
        self.assertIsNone(menu)
        self.assertEqual(menu_map, {})


class NormalizeMenuDefaultsTest(unittest.TestCase):
    def test_minimal_menu_gets_defaults(self):
        menu, _ = normalize_menu(make_menu(), 'de', 1)
        assert menu is not None
        self.assertIsNone(menu['id'])
        self.assertIsNone(menu['message'])
        self.assertFalse(menu['handle_as_template'])
        self.assertIsNone(menu['audio_file'])
        self.assertEqual(menu['language'], 'de')
        self.assertIsNone(menu['action'])
        self.assertFalse(menu['choices_are_pin'])
        self.assertEqual(menu['post_action'], {'action': 'noop'})
        self.assertEqual(menu['timeout'], DEFAULT_RING_TIMEOUT)
        self.assertFalse(menu['cache_audio'])
        self.assertFalse(menu['wait_for_audio_to_finish'])
        self.assertIsNone(menu['parent_menu'])

    def test_explicit_values_are_preserved(self):
        menu, _ = normalize_menu(make_menu(
            id='  main  ',
            message='Hello',
            handle_as_template=True,
            audio_file='/tmp/test.wav',
            language='fr',
            choices_are_pin=True,
            timeout=30,
            cache_audio=True,
            wait_for_audio_to_finish=True,
        ), 'de', 1)
        assert menu is not None
        self.assertEqual(menu['id'], 'main')
        self.assertEqual(menu['message'], 'Hello')
        self.assertTrue(menu['handle_as_template'])
        self.assertEqual(menu['audio_file'], '/tmp/test.wav')
        self.assertEqual(menu['language'], 'fr')
        self.assertTrue(menu['choices_are_pin'])
        self.assertEqual(menu['timeout'], 30.0)
        self.assertTrue(menu['cache_audio'])
        self.assertTrue(menu['wait_for_audio_to_finish'])

    def test_language_falls_back_to_default(self):
        menu, _ = normalize_menu(make_menu(language=None), 'sv', 1)
        assert menu is not None
        self.assertEqual(menu['language'], 'sv')

    def test_id_whitespace_stripped(self):
        menu, _ = normalize_menu(make_menu(id='  hello  '), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['id'], 'hello')


class PostActionTest(unittest.TestCase):
    def test_noop(self):
        menu, _ = normalize_menu(make_menu(post_action='noop'), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['post_action'], {'action': 'noop'})

    def test_none_becomes_noop(self):
        menu, _ = normalize_menu(make_menu(post_action=None), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['post_action'], {'action': 'noop'})

    def test_hangup(self):
        menu, _ = normalize_menu(make_menu(post_action='hangup'), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['post_action'], {'action': 'hangup'})

    def test_repeat_message(self):
        menu, _ = normalize_menu(make_menu(post_action='repeat_message'), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['post_action'], {'action': 'repeat_message'})

    def test_return_default_level(self):
        menu, _ = normalize_menu(make_menu(post_action='return'), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['post_action'], {'action': 'return', 'level': 1})

    def test_return_with_level(self):
        menu, _ = normalize_menu(make_menu(post_action='return 3'), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['post_action'], {'action': 'return', 'level': 3})

    def test_jump(self):
        menu, _ = normalize_menu(make_menu(post_action='jump submenu'), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['post_action'], {'action': 'jump', 'menu_id': 'submenu'})

    def test_unknown_post_action_becomes_noop(self):
        menu, _ = normalize_menu(make_menu(post_action='explode'), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['post_action'], {'action': 'noop'})


class DefaultAndTimeoutChoiceTest(unittest.TestCase):
    def test_auto_generated_default_choice(self):
        menu, _ = normalize_menu(make_menu(), 'en', 0)
        assert menu is not None
        default = menu['default_choice']
        assert default is not None
        self.assertEqual(default['message'], 'Unknown option')
        self.assertEqual(default['post_action'], {'action': 'return', 'level': 1})
        self.assertIs(default['parent_menu'], menu)

    def test_auto_generated_timeout_choice(self):
        menu, _ = normalize_menu(make_menu(), 'en', 0)
        assert menu is not None
        timeout = menu['timeout_choice']
        assert timeout is not None
        self.assertIsNone(timeout['message'])
        self.assertEqual(timeout['post_action'], {'action': 'hangup'})
        self.assertIs(timeout['parent_menu'], menu)

    def test_custom_default_choice(self):
        menu, _ = normalize_menu(make_menu(choices={
            '1': make_menu(message='Option 1'),
            'default': make_menu(message='Try again'),
        }), 'en', 0)
        assert menu is not None
        default = menu['default_choice']
        assert default is not None
        self.assertEqual(default['message'], 'Try again')
        # The 'default' key should be removed from regular choices
        assert menu['choices'] is not None
        self.assertNotIn('default', menu['choices'])

    def test_custom_timeout_choice(self):
        menu, _ = normalize_menu(make_menu(choices={
            '1': make_menu(message='Option 1'),
            'timeout': make_menu(message='Timed out', post_action='hangup'),
        }), 'en', 0)
        assert menu is not None
        timeout = menu['timeout_choice']
        assert timeout is not None
        self.assertEqual(timeout['message'], 'Timed out')
        assert menu['choices'] is not None
        self.assertNotIn('timeout', menu['choices'])


class ChoicesTest(unittest.TestCase):
    def test_choices_normalized(self):
        menu, _ = normalize_menu(make_menu(choices={
            1: make_menu(message='First'),
            2: make_menu(message='Second'),
        }), 'en', 0)
        assert menu is not None
        assert menu['choices'] is not None
        self.assertIn('1', menu['choices'])
        self.assertIn('2', menu['choices'])
        self.assertEqual(menu['choices']['1']['message'], 'First')
        self.assertEqual(menu['choices']['2']['message'], 'Second')

    def test_choice_keys_lowercased(self):
        menu, _ = normalize_menu(make_menu(choices={
            'A': make_menu(message='Alpha'),
        }), 'en', 0)
        assert menu is not None
        assert menu['choices'] is not None
        self.assertIn('a', menu['choices'])
        self.assertNotIn('A', menu['choices'])

    def test_nested_choices_parent_set(self):
        menu, _ = normalize_menu(make_menu(choices={
            '1': make_menu(message='Sub'),
        }), 'en', 0)
        assert menu is not None
        assert menu['choices'] is not None
        sub = menu['choices']['1']
        self.assertIs(sub['parent_menu'], menu)

    def test_no_choices_gives_empty_dict(self):
        menu, _ = normalize_menu(make_menu(choices=None), 'en', 0)
        assert menu is not None
        self.assertEqual(menu['choices'], {})


class MenuMapTest(unittest.TestCase):
    def test_menu_map_from_ids(self):
        _, menu_map = normalize_menu(make_menu(id='root', choices={
            '1': make_menu(id='child1', message='C1'),
            '2': make_menu(id='child2', message='C2'),
        }), 'en', 0)
        self.assertIn('root', menu_map)
        self.assertIn('child1', menu_map)
        self.assertIn('child2', menu_map)
        self.assertEqual(menu_map['child1']['message'], 'C1')

    def test_menu_map_excludes_none_ids(self):
        _, menu_map = normalize_menu(make_menu(choices={
            '1': make_menu(message='no id'),
        }), 'en', 0)
        self.assertEqual(menu_map, {})

    def test_menu_map_nested(self):
        _, menu_map = normalize_menu(make_menu(id='root', choices={
            '1': make_menu(id='level1', choices={
                '1': make_menu(id='level2'),
            }),
        }), 'en', 0)
        self.assertIn('root', menu_map)
        self.assertIn('level1', menu_map)
        self.assertIn('level2', menu_map)


class DefaultTimeoutChoiceSuppressionTest(unittest.TestCase):
    """Menus that ARE the default/timeout choice should not get their own default/timeout."""

    def test_default_choice_has_no_own_default_or_timeout(self):
        menu, _ = normalize_menu(make_menu(choices={
            '1': make_menu(message='Option 1'),
            'default': make_menu(message='Error'),
        }), 'en', 0)
        assert menu is not None
        default = menu['default_choice']
        assert default is not None
        self.assertIsNone(default['default_choice'])
        self.assertIsNone(default['timeout_choice'])

    def test_timeout_choice_has_no_own_default_or_timeout(self):
        menu, _ = normalize_menu(make_menu(choices={
            '1': make_menu(message='Option 1'),
            'timeout': make_menu(message='Bye'),
        }), 'en', 0)
        assert menu is not None
        timeout = menu['timeout_choice']
        assert timeout is not None
        self.assertIsNone(timeout['default_choice'])
        self.assertIsNone(timeout['timeout_choice'])


class PrettyPrintMenuTest(unittest.TestCase):
    def test_none_menu(self, ):
        # Should not raise
        pretty_print_menu(None)

    def test_with_menu(self):
        menu, _ = normalize_menu(make_menu(message='Hello'), 'en', 0)
        # Should not raise
        pretty_print_menu(menu)
