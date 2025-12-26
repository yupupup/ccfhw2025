try:
    import opentuner
    from opentuner import ConfigurationManipulator
    from opentuner.search.manipulator import IntegerParameter, BooleanParameter
    from opentuner import MeasurementInterface
    from opentuner import Result
except ImportError:
    opentuner = None
    # Define dummy classes to avoid NameError if imported but not used (or handled by caller)
    class MeasurementInterface: pass

class V8TunerGen(MeasurementInterface):
    """
    OpenTuner MeasurementInterface for V8 tuning.
    """
    def __init__(self, args, runner, config_generator, default_score, result_callback=None):
        """
        args: OpenTuner arguments
        runner: BenchmarkRunner instance
        config_generator: ConfigGenerator instance
        default_score: float, score of default configuration
        result_callback: function(config_vector, ratio, score) -> None
        """
        super().__init__(args)
        self.runner = runner
        self.config_generator = config_generator
        self.default_score = default_score
        self.result_callback = result_callback

    def manipulator(self):
        manipulator = ConfigurationManipulator()
        for param in self.config_generator.parameter_space:
            if param.is_bool():
                manipulator.add_parameter(BooleanParameter(param.name))
            elif param.is_int():
                manipulator.add_parameter(IntegerParameter(param.name, param.min, param.max))
        return manipulator

    def run(self, desired_result, input, limit):
        cfg = desired_result.configuration.data
        
        # Convert OpenTuner config to dict
        config = {}
        for param in self.config_generator.parameter_space:
            val = cfg[param.name]
            config[param.name] = val

        # Run benchmark
        # We might want to pass repeats if the runner supports it, or handle repeats here.
        # The original code handled repeats in run_benchmark.
        # Let's assume runner.run takes config.
        # If we need repeats, we can loop here or runner can handle it.
        # For now, let's assume runner.run does one run or we loop here.
        # The original code had 'repeats' arg in run_benchmark.
        # I should probably add repeats to runner.run or handle it here.
        # Let's check BenchmarkRunner.run signature. It takes **kwargs.
        # I'll loop here for repeats if needed, or better, let's assume the runner is configured or we pass it.
        # The original code passed repeats to run_benchmark.
        # I'll add a repeats parameter to __init__ or use a default.
        
        # Let's use a simple loop for repeats here to match original logic
        # But wait, BenchmarkRunner.run returns a single score?
        # The original run_benchmark returned average score.
        # I should probably implement average logic in BenchmarkRunner or here.
        # Let's implement it here for now, or assume runner handles it.
        # Actually, BenchmarkRunner.run is abstract. OctaneRunner.run calls subprocess.
        # I should probably add a helper to run with repeats.
        
        scores = []
        repeats = getattr(self.args, 'repeats', 1) # Assume args has repeats or default to 1
        
        for _ in range(repeats):
            score = self.runner.run(config)
            if score is not None:
                scores.append(score)
        
        if not scores:
            return Result(time=float('inf')) # Penalize failure

        avg_score = sum(scores) / len(scores)
        
        # Calculate ratio
        ratio = avg_score / self.default_score
        config_vector = self.config_generator.get_config_vector_from_dict(config)
        
        # Callback
        if self.result_callback:
            self.result_callback(config_vector, ratio, avg_score)
            
        print(f"OpenTuner Sample: Ratio={ratio:.4f} (Score={avg_score})")

        # OpenTuner minimizes time. We maximize score.
        return Result(time=-avg_score)

    def save_final_config(self, configuration):
        pass
