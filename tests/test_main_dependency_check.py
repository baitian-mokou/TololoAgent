import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

import main


class MainDependencyCheckTests(unittest.TestCase):
    def test_missing_dependencies_print_install_command_without_pip_install(self):
        with mock.patch.object(main, "_missing_required_dependencies", return_value=["ttkbootstrap"]):
            with mock.patch("subprocess.run") as run:
                output = io.StringIO()
                with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                    main._exit_if_required_dependencies_missing()

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("缺少 Python 依赖", output.getvalue())
        self.assertIn("python -m pip install -r requirements.txt", output.getvalue())
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
