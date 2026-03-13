import json
import os
import sys
import time
import random
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from scipy.stats import norm

# Add the project root to the Python path
# The current file is in scripts/comptuner4js, so we need to go up two levels
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scripts.utils.parameters import ParameterSpace
from scripts.utils.config_generator import ConfigGenerator
from scripts.utils.benchmark_runner import OctaneRunner

initial_sample = 30
epochs = 100

class V8CompTuner:
    def __init__(self, parameter_space: ParameterSpace, runner: OctaneRunner, log_file: str, code_embeddings: dict, random_seed: int = 456):
        self.parameter_space = parameter_space
        self.runner = runner
        self.log_file = log_file
        self.code_embeddings = code_embeddings
        self.dim = len(parameter_space.get_parameters())
        self.config_generator = ConfigGenerator(parameter_space)
        self.random_seed = random_seed
        self.baseline_scores = {}  # 改进点：改为字典存储 {code_id: baseline_score}
        
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        # Fetch baseline score for each benchmark
        print("Fetching baseline scores for all benchmarks...")
        for benchmark_name in self.code_embeddings.keys():
            try:
                score = self.runner.run({}, benchmark=benchmark_name)
                self.baseline_scores[benchmark_name] = score
                print(f"  - Baseline score for {benchmark_name}: {score}")
            except Exception as e:
                print(f"  - Error fetching baseline score for {benchmark_name}: {e}")
                self.baseline_scores[benchmark_name] = None

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

    def get_objective_score(self, vector, benchmark_name):
        """
        Obtain the score (speedup or raw score)
        改进：显式传入 benchmark_name 或 code_identifier
        """

        config = self.vector_to_config(vector)
        
        # Run benchmark
        # Note: OctaneRunner.run takes config and optional benchmark name.
        # Here we assume running the full suite or a default benchmark if not specified.
        # For simplicity, we'll run whatever the runner is configured for.
        # If the runner needs a specific benchmark, it should be handled or passed.
        # Assuming runner.run(config) works.
        
        try:
            score = self.runner.run(config, benchmark=benchmark_name)
        except Exception as e:
            print(f"Error running benchmark: {e}")
            score = 0

        if score is None:
            score = 0
            
        # If we want speedup, we need a baseline.
        # For now, let's just return the raw score as the objective to maximize.
        # If baseline is set, we can return speedup.
        baseline = self.baseline_scores.get(benchmark_name)
        if baseline and baseline > 0:
            return score / baseline
        
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

    def getPrecision(self, model, seq, code_embedding, benchmark_name):
        """
        :param model: RandomForest Model
        :param seq: 11-dimensional parameter vector
        :param code_embedding: code embedding vector
        :return: the precision of a sequence and true speedup
        """
        true_running = self.get_objective_score(seq, benchmark_name)

        # --- Feature Concatenation ---
        # Concatenate the 768-dim code embedding with the 11-dim param vector
        full_vector = np.concatenate((code_embedding, seq)).reshape(1, -1)

        estimators = model.estimators_
        res = []
        for e in estimators:
            # Predict using the concatenated vector
            tmp = e.predict(full_vector)
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

    def savAcc(self, all_acc):
        # 使用 f-string 动态构建文件名
        file_name = f"all_acc-{epochs}.json"
        # 如果想包含多个参数，可以写成：f"all_acc-ep{epochs}-lr{lr}.json"

        with open(file_name, "w") as f:
            json.dump(all_acc, f)

        print(f"文件已保存为: {file_name}")

        # 创建画布
        plt.figure(figsize=(10, 6))

        # 绘图：横坐标默认为索引，纵坐标为值
        plt.plot(all_acc, marker='o', linestyle='-', color='b', label='Accuracy Value')

        # 添加标题和标签
        plt.title('Visualization of all_acc Indices and Values', fontsize=14)
        plt.xlabel('Index', fontsize=12)
        plt.ylabel('Value (np.float64)', fontsize=12)

        # 显示网格以方便观察
        plt.grid(True, linestyle='--', alpha=0.7)

        # 显示图例
        plt.legend()

        # 展示图表S
        plt.savefig(f"all_acc-{epochs}.png")

    def build_RF_model(self):
        """
        Builds the Random Forest model using Active Learning.
        :return: model, initial_indep, initial_dep
        """

        # 初始的自变量集合，模型输入（X）,列表的每个元素存储embedding+V8config
        inital_indep = [] # This will store the full 64+11-dim vectors
        #  初始的因变量集合,标签(Y),真实性能得分
        initial_dep = []
        ts_tem = []
        
        # randomly sample initial training instances
        time_begin = time.time()
        param_vectors_for_eval = []
        while len(inital_indep) < initial_sample:
            # Use ConfigGenerator to generate a random 11-dim parameter vector
            _, param_vector = self.config_generator.generate_random_config()
            
            # Randomly select a benchmark and its corresponding embedding
            benchmark_name, code_embedding = random.choice(list(self.code_embeddings.items()))

            # Concatenate with code embedding to create the full feature vector
            full_vector = np.concatenate((code_embedding, param_vector))

            # Check for duplicates in the full vector list
            if not any(np.array_equal(full_vector, x) for x in inital_indep):
                inital_indep.append(full_vector)
                # Store tuple of (param_vector, benchmark_name) for evaluation
                param_vectors_for_eval.append((param_vector, benchmark_name))

        # Evaluate initial instances
        initial_dep = [self.get_objective_score(p_vec, b_name) for p_vec, b_name in param_vectors_for_eval]

        ts_tem.append(time.time() - time_begin)

        print('Generated initial instances. \ninitial_indep: {}, \ninitial_dep: {}'.format(inital_indep, initial_dep))
        
        best_perf = max(initial_dep)
        best_seq_idx = initial_dep.index(best_perf)
        ss = '{}: best_seq {}, best_per {}'.format(str(round(ts_tem[-1])), str(best_perf), str(inital_indep[best_seq_idx][-self.dim:]))
        self.write_log(ss)
        
        all_acc = []
        model = RandomForestRegressor(random_state=self.random_seed)
        model.fit(np.array(inital_indep), np.array(initial_dep))
        
        rec_size = initial_sample
        while rec_size < epochs:
            global_best = max(initial_dep)
            estimators = model.estimators_# 获取随机森林中的每一棵决策树
            
            # Generate neighbors (candidates)
            neighbors = [] # List of (param_vector, embedding)
            while len(neighbors) < 30000:
                # Use ConfigGenerator for random sampling
                _, vector = self.config_generator.generate_random_config()
                benchmark_name, embedding = random.choice(list(self.code_embeddings.items()))
                # Store benchmark_name along with vector and embedding
                neighbors.append((vector, embedding, benchmark_name))
                # Note: Original code checked for duplicates in neighbors, which is O(N^2) for list.
                # For 30k, that's slow. We'll skip strict duplicate check for speed or use a set of tuples.
            
            # Predict
            # For prediction, concatenate the code embedding with each neighbor
            full_neighbors = np.array([np.concatenate((emb, vec)) for vec, emb, _ in neighbors])
            
            pred = []
            for e in estimators:
                pred.append(e.predict(full_neighbors))# 让每一棵树都对30000个候选集预测
            
            # get_ei 函数根据所有树的预测结果的均值和标准差，计算每个候选的“期望提升”值。
            # 如果一个候选的所有树预测结果都差不多且很高，EI会高；
            # 如果预测结果差异很大（高不确定性），EI也会高。
            acq_val_incumbent = self.get_ei(pred, global_best)
            # ei_for_current should store the (param_vector, embedding) tuple for later use
            ei_for_current = [[pair, a] for a, pair in zip(acq_val_incumbent, neighbors)]
            merged_predicted_objectives = sorted(ei_for_current, key=lambda x: x[1], reverse=True)

            print('Generated 30000 neighbors and get their EI values')
            
            
            acc = 0
            flag = False
            for x in merged_predicted_objectives:# merged_predicted_objectives = sorted(...): 将候选按EI值从高到低排序
                if flag:
                    break
                
                # x[0] is the (param_vector, embedding, benchmark_name) tuple.
                param_vector_to_add, embedding_to_add, benchmark_name_to_add = x[0]
                full_vector_to_add = np.concatenate((embedding_to_add, param_vector_to_add))

                is_in_indep = False
                for existing_full_vector in inital_indep:
                    if np.array_equal(full_vector_to_add, existing_full_vector):
                        is_in_indep = True
                        break
                
                if not is_in_indep:
                    inital_indep.append(full_vector_to_add)
                    # Pass benchmark_name_to_add to getPrecision
                    acc,label = self.getPrecision(model, param_vector_to_add, embedding_to_add, benchmark_name_to_add)
                    initial_dep.append(label)
                    all_acc.append(acc)
                    print(f'[epoch:{len(all_acc)}] Append new sample: {param_vector_to_add}, \nacc: {acc}, label: {label}')
                    # print('Append new sample: {}, acc: {}, label: {}'.format(param_vector_to_add, acc, label))
                    flag = True
            
            rec_size += 1
            
            # if acc > 0.05: 如果模型的预测误差较大，说明模型在当前区域还不太准。
            # self.selectByDistribution(...): 为了避免陷入局部最优，代码会启动一个探索机制。
            # 它会根据EI的分布进行带权随机采样，而不是总选择EI最高的，从而有机会选择一些次优但具有探索价值的样本。
            if acc > 0.05:
                indx = self.selectByDistribution(merged_predicted_objectives)
                
                # Ensure we don't pick something already in indep
                # Potential infinite loop if everything is in indep, but unlikely with 30k neighbors
                max_retries = 100
                retries = 0
                while retries < max_retries:
                    candidate_param_vector, candidate_embedding, _ = merged_predicted_objectives[indx][0]
                    candidate_full_vector = np.concatenate((candidate_embedding, candidate_param_vector))
                    
                    is_in_indep = False
                    for existing_full_vector in inital_indep:
                        if np.array_equal(candidate_full_vector, existing_full_vector):
                            is_in_indep = True
                            break
                    
                    if not is_in_indep:
                        break
                        
                    indx = self.selectByDistribution(merged_predicted_objectives)
                    retries += 1
                
                if retries < max_retries:
                    param_vector_to_add, embedding_to_add, benchmark_name_to_add = merged_predicted_objectives[indx][0]
                    full_vector_to_add = np.concatenate((embedding_to_add, param_vector_to_add))
                    inital_indep.append(full_vector_to_add)
                    
                    acc, label = self.getPrecision(model, param_vector_to_add, embedding_to_add, benchmark_name_to_add)
                    initial_dep.append(label)
                    all_acc.append(acc)
                    print(f'[epoch:{len(all_acc)}] Append new sample: {param_vector_to_add}, \nacc: {acc}, label: {label}')
                    # print('[epoch:{}]Append new sample: {}, acc: {}, label: {}'.format(len(all_acc),param_vector_to_add, acc, label))
                    rec_size += 1

            ts_tem.append(time.time() - time_begin)
            
            best_perf = max(initial_dep)
            best_seq_idx = initial_dep.index(best_perf)
            ss = '{}: best_seq {}, best_per {}'.format(str(round(ts_tem[-1])), str(best_perf), str(inital_indep[best_seq_idx][-self.dim:]))
            self.write_log(ss)

            print('Updating the model, np.mean(all_acc)={}'.format(np.mean(all_acc)))
            
            # inital_indep (特征集) 和 initial_dep (标签集) 被转换成NumPy数组，并一起传递给随机森林模型的 fit 方法来训练模型。
            model = RandomForestRegressor(random_state=self.random_seed)
            model.fit(np.array(inital_indep), np.array(initial_dep))
            
            # if rec_size < epochs*2 and len(all_acc) > 0 and np.mean(all_acc) < 0.04:
            #     break

        self.savAcc(all_acc);            
        

        return model, inital_indep, initial_dep
