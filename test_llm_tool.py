"""The assistant bridge must preserve failures, prior outputs and JSON boundaries."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('llm_tool', Path(__file__).parent / 'examples/llm_tool.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root / '中文 & title.wav'
        self.audio.write_bytes(b'fixture, not decoded in these wrapper unit tests')

    def fake(self, status='not_music', code=0, task='semantics'):
        def execute(arguments, timeout):
            self.assertEqual(arguments[0], str(self.audio.resolve()))
            folder = Path(arguments[arguments.index('-o') + 1])
            folder.mkdir()
            summary = {'status': status, 'warnings': ['uncalibrated']}
            if task == 'all':
                summary = {'key': 'candidate', 'semantics': summary}
                (folder / 'report.json').write_text('{}')
                (folder / 'score_p1.svg').write_text('<svg/>')
            else:
                (folder / 'semantics.json').write_text('{}')
            (folder / 'summary.json').write_text(json.dumps(summary))
            return subprocess.CompletedProcess(arguments, code, stdout='progress\n', stderr='')
        return execute

    def test_missing_input_does_not_create_output(self):
        response, code = tool.analyze(self.root / 'missing.wav', self.root / 'out')
        self.assertEqual(code, 2)
        self.assertEqual(response['status'], 'error')
        self.assertFalse((self.root / 'out').exists())

    def test_non_music_is_completed_but_remains_non_music(self):
        with patch.object(tool, 'execute', self.fake()):
            response, code = tool.analyze(self.audio, self.root / 'out')
        self.assertEqual(code, 0)
        self.assertEqual(response['status'], 'completed')
        self.assertEqual(response['summary']['status'], 'not_music')
        self.assertTrue(Path(response['query_report']).is_file())

    def test_repeated_calls_create_new_folders_and_preserve_first(self):
        with patch.object(tool, 'execute', self.fake()):
            first, _ = tool.analyze(self.audio, self.root / 'out')
            second, _ = tool.analyze(self.audio, self.root / 'out')
        self.assertNotEqual(first['output_dir'], second['output_dir'])
        self.assertTrue(Path(first['output_dir'], 'summary.json').is_file())

    def test_missing_models_keeps_unavailable_and_exit_four(self):
        with patch.object(tool, 'execute', self.fake('unavailable', 4)):
            response, code = tool.analyze(self.audio, self.root / 'out')
        self.assertEqual((response['status'], code), ('unavailable', 4))

    def test_joint_success_with_semantic_failure_is_partial(self):
        with patch.object(tool, 'execute', self.fake('unavailable', 0, 'all')):
            response, code = tool.analyze(self.audio, self.root / 'out', 'all')
        self.assertEqual(code, 0)
        self.assertEqual(response['status'], 'partial')
        self.assertEqual(response['summary']['semantics']['status'], 'unavailable')
        self.assertEqual(len(response['artifacts']['svg_pages']), 1)

    def test_invalid_query_does_not_launch_process(self):
        report = self.root / 'report.json'
        report.write_text('{}')
        with patch.object(tool, 'execute') as execute:
            response, code = tool.query(report, 3, 2)
        self.assertEqual(code, 2)
        execute.assert_not_called()

    def test_child_uses_argument_list_without_shell(self):
        with patch.object(tool.subprocess, 'run') as run:
            tool.execute([str(self.audio), '-o', 'destination'], 30)
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertIn(str(self.audio), args[0])
        self.assertIs(kwargs['shell'], False)
        self.assertEqual(kwargs['cwd'], tool.ROOT)

    def test_timeout_is_explicit(self):
        with patch.object(tool, 'execute', side_effect=subprocess.TimeoutExpired('local', 1)):
            response, code = tool.analyze(self.audio, self.root / 'out')
        self.assertEqual((response['status'], code), ('error', 2))
        self.assertIn('timed out', response['error'])


if __name__ == '__main__':
    unittest.main()
