import subprocess
import re
import os
from abc import ABC, abstractmethod

class BenchmarkRunner(ABC):
    """
    Abstract base class for benchmark runners.
    """
    @abstractmethod
    def run(self, **kwargs):
        """
        Executes the benchmark and returns the score.
        """
        pass

    @property
    def metric_direction(self):
        """
        Returns 'higher-better' or 'lower-better'.
        Default is 'higher-better' (e.g. score).
        """
        return 'higher-better'

class BenchmarkRunnerD8(BenchmarkRunner):
    """
    Runner for d8-based benchmarks.
    """
    def __init__(self, d8_path):
        self.d8_path = d8_path

    @abstractmethod
    def build_cmd(self, config, **kwargs):
        cmd = [self.d8_path]
        
        # Add flags from config
        for key, val in config.items():
            if val is True:
                cmd.append(f"--{key}")
            elif val is False:
                cmd.append(f"--no-{key}")
            else:
                cmd.append(f"--{key}={val}")
        return cmd

    @abstractmethod
    def parse_output(self, output):
        """
        Parses the output to extract the score.
        """
        pass

    def run(self, config, **kwargs):
        cmd = self.build_cmd(config, **kwargs)
        
        try:
            # Check if cmd is a list of strings
            if not isinstance(cmd, list):
                 raise ValueError("Command must be a list of strings")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120, # Default timeout, maybe make configurable
                cwd=kwargs.get('cwd', None)
            )

            if result.returncode != 0:
                print(f"Error running benchmark: {result.stderr}\ncmd: {cmd}") # Optional logging
                return None

            return self.parse_output(result.stdout)

        except subprocess.TimeoutExpired:
            return None
        except Exception as e:
            print(f"Exception during benchmark execution: {e}")
            return None

class OctaneRunner(BenchmarkRunnerD8):
    """
    Runner for the Octane benchmark suite.
    """
    def __init__(self, d8_path, octane_dir):
        super().__init__(d8_path)
        self.octane_dir = octane_dir

    def build_cmd(self, config, benchmark=None, **kwargs):
        cmd = super().build_cmd(config, **kwargs)

        if benchmark:
            cmd.append("base.js")
            
            # Handle dependencies
            if benchmark == 'zlib':
                cmd.append("zlib.js")
                cmd.append("zlib-data.js")
            elif benchmark == 'typescript':
                cmd.append("typescript.js")
                cmd.append("typescript-input.js")
                cmd.append("typescript-compiler.js")
            elif benchmark == 'gbemu':
                cmd.append("gbemu-part1.js")
                cmd.append("gbemu-part2.js")
            else:
                cmd.append(f"{benchmark}.js")
                
            cmd.append("-e")
            js_code = (
                "function PrintResult(name, result) { print(name + ': ' + result); }; "
                "function PrintScore(score) { print('Score: ' + score); }; "
                "BenchmarkSuite.RunSuites({NotifyResult: PrintResult, NotifyScore: PrintScore});"
            )
            cmd.append(js_code)
        else:
            cmd.append("run.js")
            
        return cmd

    def parse_output(self, output):
        match = re.search(r"Score \(version \d+\): (\d+)", output)
        if not match:
            match = re.search(r"Score: (\d+)", output)
            
        if match:
            return float(match.group(1))
        else:
            return None

    def run(self, config, benchmark=None):
        # Override run to pass cwd=self.octane_dir
        return super().run(config, benchmark=benchmark, cwd=self.octane_dir)


class BenchmarkRunnerBrowser(BenchmarkRunner):
    """
    Runner for browser-based benchmarks.
    """
    def __init__(self, browser_path):
        self.browser_path = browser_path

    def run(self, **kwargs):
        # Placeholder for browser execution logic (e.g., using Puppeteer or Selenium)
        raise NotImplementedError("Browser benchmark running is not yet implemented.")
