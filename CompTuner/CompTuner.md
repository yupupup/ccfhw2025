[zhumxxx/CompTuner: code of paper "Compiler Autotuning through Multiple-phase Learning"](https://github.com/zhumxxx/CompTuner)
#### **必要参数:**

1. **`--log_file`**: 您希望保存日志的文件名。
    
    - **作用**: 脚本会把每次迭代的性能、找到的最佳编译选项等信息记录在这个文件里。
    - **示例**: `--log_file my_run.log`
2. **`--source_path`**: 您要优化的C语言源代码所在的**目录路径**。
    
    - **作用**: 脚本会编译这个目录下的所有 `.c` 文件。
    - **示例**: `--source_path /path/to/your/c_project`
3. **`--gcc_path`**: GCC编译器的完整路径。
    
    - **作用**: 指定用于编译源代码的编译器。
    - **示例**: `--gcc_path /usr/bin/gcc` (这在大多数Linux系统上是默认路径)
4. **`--flag_path`**: 一个包含待优化编译标志的文本文件路径。
    
    - **作用**: 文件内容应该是您希望脚本去尝试组合优化的GCC标志，用逗号分隔。
    - **示例**: 创建一个名为 `flags.txt` 的文件，内容为 `-fauto-inc-dec,-fbranch-count-reg,-fcombine-stack-adjustments`，然后使用 `--flag_path flags.txt`。

#### **可选参数:**

- **`--exec_param`**: 您的C程序运行时需要传递的命令行参数。
    - **作用**: 如果编译出的可执行文件需要输入参数才能运行，您需要在这里提供。
    - **示例**: 如果您的程序需要读取一个输入文件，可以设置为 `--exec_param "< input.dat"`。
---
**运行方法：**
传入四个必要参数。其中log_file是输出日志的文件名称，传入该参数会在log文件夹下生成对应的log文件
gcc_path即为GCC编译器的完整路径
在py脚本的根目录下建立flag.txt和test.c，flag.txt用于记录要调优的参数列表（以,分隔，eg.-Ofast,-funroll-loops）;test.c是用于测试的C代码程序。
执行命令如下：
```shell
python CompTuner.py --log_file myrun.log --source_path ./ --gcc_path /usr/bin/gcc --flag_path flags.txt
```

---

测试遇到问题：
1.无法传入过于庞大的C项目，尤其在包含程序的构建时。
在尝试toybox项目时，`CompTuner.py` 脚本犯了一个根本性的错误：它试图绕过项目的构建系统，只编译 `main.c`。而 `toybox` 是一个复杂的项目，需要编译 `toys/` 目录下的许多其他 `.c` 文件，并将它们全部链接在一起才能成功生成可执行文件。直接编译 `main.c` 导致所有其他命令（如 `ls`, `cat`, `who` 等）的实现代码都丢失了，从而引发了大量的 "undefined reference" 链接错误。

2.flag.txt中设定参数只能是肯定的参数，不能是以下形式的否定参数：
```shell
-fno-unroll-loops,
-fno-tree-vectorize,
```
原因：py脚本局限性
当脚本决定**禁用**某个优化时（即 `independent[i]` 为 `0`），它会尝试将一个“肯定”的标志（如 `-funroll-loops`）变成一个“否定”的标志（`-fno-unroll-loops`）。
**缺陷就在于：**
这个简单的字符串替换逻辑没有考虑到，如果 `flags.txt` 文件中**本身就包含了一个否定的标志**（例如 `-fno-unroll-loops`），会发生什么情况