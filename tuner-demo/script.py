import opentuner
from opentuner import ConfigurationManipulator
from opentuner import IntegerParameter
from opentuner import MeasurementInterface
from opentuner import Result

global_config = {
  'd8_path': '',
  'excuted_path': '',
}

class GccFlagsTuner(MeasurementInterface):

  def manipulator(self):
    manipulator = ConfigurationManipulator()
    manipulator.add_parameter(IntegerParameter('turbo-inlining', 0, 1))
    manipulator.add_parameter(IntegerParameter('use-osr', 0, 1))
    # manipulator.add_parameter(...)
    return manipulator

  def run(self, desired_result, input, limit):
    cfg = desired_result.configuration.data

    run_cmd = global_config['d8_path'] + ' ' + global_config['excuted_path']

    if cfg['turbo-inlining']:
      run_cmd += ' -turbo-inlining'
    else:
      run_cmd += ' -no-turbo-inlining'
    if cfg['use-osr']:
      run_cmd += ' -use-osr'
    else:
      run_cmd += ' -no-use-osr'
    
    # run_cmd += ' -xx-xx=' + str(VALUE)
    # ...

    # Octane 测试集的测试分数是输出内容中的最后一个数
    run_result = self.call_program(run_cmd)
    output = run_result['stdout'].decode('utf8')
    output = output[1 + output.rindex(' ') : min(output.rindex('\r'), output.rindex('\n'))]

    return Result(time=-int(output))

  def save_final_config(self, configuration):
    self.manipulator().save_to_file(configuration.data, 'cfg.json')


if __name__ == '__main__':
  argparser = opentuner.default_argparser()
  GccFlagsTuner.main(argparser.parse_args())
