import os
import time
import random
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from scipy.stats import norm

from scripts.utils.parameters import ParameterSpace
from scripts.utils.config_generator import ConfigGenerator
from scripts.utils.benchmark_runner import OctaneRunner

class V8CompTuner:
    def __init__(self, parameter_space: ParameterSpace, runner: OctaneRunner, log_file: str, random_seed: int = 456):
        self.parameter_space = parameter_space
        self.runner = runner
        self.log_file = log_file
        self.dim = len(parameter_space.get_parameters())
        self.config_generator = ConfigGenerator(parameter_space)
        self.random_seed = random_seed
        self.baseline_score = None
        
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        # Fetch baseline score
        print("Fetching baseline score...")
        try:
            self.baseline_score = self.runner.run({}, benchmark='richards')
            print(f"Baseline score: {self.baseline_score}")
        except Exception as e:
            print(f"Error fetching baseline score: {e}")
            self.baseline_score = None

    def write_log(self, ss):
        """ Write to log """
        with open(self.log_file, 'a') as log:
            log.write(ss + '\n')
            log.flush()

    def vector_to_config(self, vector):
        """
        Converts a vector representation back to a configuration dictionary.
        Assumes the vector order matches parameter_space.get_parameters() order.
        """
        config = {}
        params = self.parameter_space.get_parameters()
        if len(vector) != len(params):
            raise ValueError(f"Vector length {len(vector)} does not match parameter count {len(params)}")
        
        for i, param in enumerate(params):
            val = vector[i]
            if param.is_bool():
                # Convert 0/1 back to False/True
                config[param.name] = bool(val > 0.5) # Threshold at 0.5
            elif param.is_int():
                config[param.name] = int(val)
            else: # float
                config[param.name] = float(val)
        return config

    def get_objective_score(self, vector):
        """
        Obtain the score (speedup or raw score).
        """
        config = self.vector_to_config(vector)
        
        # Run benchmark
        # Note: OctaneRunner.run takes config and optional benchmark name.
        # Here we assume running the full suite or a default benchmark if not specified.
        # For simplicity, we'll run whatever the runner is configured for.
        # If the runner needs a specific benchmark, it should be handled or passed.
        # Assuming runner.run(config) works.
        
        try:
            score = self.runner.run(config, benchmark='richards')
        except Exception as e:
            print(f"Error running benchmark: {e}")
            score = 0

        if score is None:
            score = 0
            
        # If we want speedup, we need a baseline.
        # For now, let's just return the raw score as the objective to maximize.
        # If baseline is set, we can return speedup.
        if self.baseline_score:
             return score / self.baseline_score
        
        return score

    def get_ei(self, preds, eta):
        """
        :param preds: sequences' speedup for EI
        :param eta: global best speedup
        :return: the EI for a sequence
        """
        preds = np.array(preds).transpose(1, 0)
        m = np.mean(preds, axis=1)
        s = np.std(preds, axis=1)

        def calculate_f(eta, m, s):
            # Original formula from CompTuner.py
            # Note: The user explicitly asked to KEEP the original formula.
            # Original: z = (eta - m) / s
            #           return (eta - m) * norm.cdf(z) + s * norm.pdf(z)
            z = (eta - m) / s
            return (eta - m) * norm.cdf(z) + s * norm.pdf(z)

        if np.any(s == 0.0):
            s_copy = np.copy(s)
            s[s_copy == 0.0] = 1.0
            f = calculate_f(eta, m, s)
            f[s_copy == 0.0] = 0.0
        else:
            f = calculate_f(eta, m, s)
        return f

    def getPrecision(self, model, seq):
        """
        :param model: RandomForest Model
        :param seq: sequence
        :return: the precision of a sequence and true speedup
        """
        true_running = self.get_objective_score(seq)
        estimators = model.estimators_
        res = []
        for e in estimators:
            tmp = e.predict(np.array(seq).reshape(1, -1))
            res.append(tmp)
        acc_predict = np.mean(res)
        
        if true_running == 0:
            return 1.0, 0 # Avoid division by zero, treat as high error?
            
        return abs(true_running - acc_predict) / true_running, true_running

    def selectByDistribution(self, merged_predicted_objectives):
        """
        :param merged_predicted_objectives: the sequences' EI and the sequences
        :return: the selected sequence index
        """
        diffs = [abs(perf - merged_predicted_objectives[0][1]) for seq, perf in merged_predicted_objectives]
        diffs_sum = sum(diffs)
        if diffs_sum == 0:
            probabilities = [1.0 / len(diffs)] * len(diffs)
        else:
            probabilities = [diff / diffs_sum for diff in diffs]
        
        index = list(range(len(diffs)))
        idx = np.random.choice(index, p=probabilities)
        return idx

    def build_RF_model(self):
        """
        Builds the Random Forest model using Active Learning.
        :return: model, initial_indep, initial_dep
        """
        inital_indep = []
        initial_dep = []
        ts_tem = []
        
        # randomly sample initial training instances
        time_begin = time.time()
        while len(inital_indep) < 2:
            # Use ConfigGenerator to generate random config
            config, vector = self.config_generator.generate_random_config()

            print(vector)

            # Check for duplicates (simple list check)
            if not any(np.array_equal(vector, x) for x in inital_indep):
                inital_indep.append(vector)

        # Evaluate initial instances
        initial_dep = [self.get_objective_score(indep) for indep in inital_indep]

        ts_tem.append(time.time() - time_begin)

        print('Generated initial instances. initial_indep: {}, initial_dep: {}'.format(inital_indep, initial_dep))
        
        best_perf = max(initial_dep)
        best_seq_idx = initial_dep.index(best_perf)
        ss = '{}: best_seq {}, best_per {}'.format(str(round(ts_tem[-1])), str(best_perf), str(inital_indep[best_seq_idx]))
        self.write_log(ss)
        
        all_acc = []
        model = RandomForestRegressor(random_state=self.random_seed)
        model.fit(np.array(inital_indep), np.array(initial_dep))
        
        rec_size = 2
        while rec_size < 50:
            global_best = max(initial_dep)
            estimators = model.estimators_
            
            # Generate neighbors (candidates)
            neighbors = []
            while len(neighbors) < 30000:
                # Use ConfigGenerator for random sampling
                _, vector = self.config_generator.generate_random_config()
                # We might want to optimize this check for 30k items
                neighbors.append(vector)
                # Note: Original code checked for duplicates in neighbors, which is O(N^2) for list.
                # For 30k, that's slow. We'll skip strict duplicate check for speed or use a set of tuples.
            
            # Predict
            pred = []
            for e in estimators:
                pred.append(e.predict(np.array(neighbors)))
            
            acq_val_incumbent = self.get_ei(pred, global_best)
            ei_for_current = [[i, a] for a, i in zip(acq_val_incumbent, neighbors)]
            merged_predicted_objectives = sorted(ei_for_current, key=lambda x: x[1], reverse=True)

            print('Generated 30000 neighbors and get their EI values')
            
            acc = 0
            flag = False
            for x in merged_predicted_objectives:
                if flag:
                    break
                
                # Check if x[0] (vector) is already in inital_indep
                # Using np.array_equal for correctness
                is_in_indep = False
                for existing in inital_indep:
                    if np.array_equal(x[0], existing):
                        is_in_indep = True
                        break
                
                if not is_in_indep:
                    inital_indep.append(x[0])
                    acc, lable = self.getPrecision(model, x[0])
                    initial_dep.append(lable)
                    all_acc.append(acc)
                    print('Append new sample: {}, acc: {}, label: {}'.format(x[0], acc, lable))
                    flag = True
            
            rec_size += 1
            
            if acc > 0.05:
                indx = self.selectByDistribution(merged_predicted_objectives)
                
                # Ensure we don't pick something already in indep
                # Potential infinite loop if everything is in indep, but unlikely with 30k neighbors
                max_retries = 100
                retries = 0
                while retries < max_retries:
                    candidate = merged_predicted_objectives[indx][0]
                    is_in_indep = False
                    for existing in inital_indep:
                        if np.array_equal(candidate, existing):
                            is_in_indep = True
                            break
                    
                    if not is_in_indep:
                        break
                        
                    indx = self.selectByDistribution(merged_predicted_objectives)
                    retries += 1
                
                if retries < max_retries:
                    inital_indep.append(merged_predicted_objectives[indx][0])
                    acc, label = self.getPrecision(model, merged_predicted_objectives[int(indx)][0])
                    initial_dep.append(label)
                    all_acc.append(acc)
                    print('Append new sample: {}, acc: {}, label: {}'.format(merged_predicted_objectives[int(indx)][0], acc, label))
                    rec_size += 1

            ts_tem.append(time.time() - time_begin)
            
            best_perf = max(initial_dep)
            best_seq_idx = initial_dep.index(best_perf)
            ss = '{}: best_seq {}, best_per {}'.format(str(round(ts_tem[-1])), str(best_perf), str(inital_indep[best_seq_idx]))
            self.write_log(ss)

            print('Updating the model, np.mean(all_acc)={}'.format(np.mean(all_acc)))
            
            model = RandomForestRegressor(random_state=self.random_seed)
            model.fit(np.array(inital_indep), np.array(initial_dep))
            
            if rec_size < 100 and len(all_acc) > 0 and np.mean(all_acc) < 0.04:
                break
                
        return model, inital_indep, initial_dep
