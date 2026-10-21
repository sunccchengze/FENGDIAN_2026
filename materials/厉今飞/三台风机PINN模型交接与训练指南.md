<!-- markitdown-mirror: source="三台风机PINN模型交接与训练指南.docx" sha256="5d8bdce36636" generated="2026-10-05" | 只读镜像，正文由 microsoft/markitdown 自动转换，以同目录原文件为准；重新生成：python3 tools/markitdown_sync.py -->

三台风机 PINN 模型交接指南

用于项目打包 数据准备 后续训练与优化调用
交接日期 2026年10月3日

我们已完成原预训练模型的加载、隐藏层冻结，以及九个控制输入和六个目标输出的结构改造，实际项目运行检查已通过。接收同学可以直接使用压缩包中的待训练模型，填写项目配置并准备数据，随后训练新增参数。

**当前交付阶段为待数据训练。**新增部分尚未学习真实工况与功率、有效风速之间的关系，预测准确性尚未验证。完成训练和独立测试后，再将模型用于优化。

# 1 已完成的工作与适用范围

| **部分** | **参数数量** | **状态** |
| --- | --- | --- |
| 原模型全部参数 | 3,090,200 | 原模型保留用于追溯 |
| 保留的原有隐藏层 | 3,087,200 | 原权重冻结 |
| 新增控制输入连接 | 6,300 | 参加后续训练 |
| 新的六个输出层 | 18,006 | 参加后续训练 |
| 合计可训练参数 | 24,306 | 约为原模型参数量的0.79% |

改造复用了原网络的共享隐藏层和全部六个特征分支。原第一隐藏层增加九个控制输入的连接，原坐标连接权重和偏置继续冻结；没有新增独立的小神经网络或额外隐藏层。三台机组共用原网络权重，各自的输出层读取所在位置的特征。

实际运行已通过原特征一致性、九个输入连接的梯度与作用路径、原权重不变、保存重载一致性检查。检查中的临时参数变化已恢复。新增输入连接初始为零，真实控制作用需要后续数据训练。

本版面向固定三台机组布置、固定机型和固定来流环境。入口风速、风向、湍流强度还没有作为可变输入接入。原预训练模型对应9 m/s、四台风机的源工况，迁移到本项目三台机组的准确性需要验证。

后续训练采用有标签的迁移学习，不运行原仓库的RANS和k-ε方程残差训练流程。可训练参数减少不等于计算时间按相同比例减少；原隐藏层仍参与前向计算和新增输入连接的反向传播。

# 2 发件人怎样打包

**最省事的办法：**将本指南放进已完成改造的项目根目录，压缩整个 PINNs\_multi\_turbine\_wake\_simulation-outputchange 文件夹，再交给接收同学。这样能一并保留原代码、预训练权重、模型和配置。

当前用户电脑上的项目根目录如下。接收方可解压到自己的位置，不必复现这个用户路径。

C:\Users\Ice-d\Desktop\pinnmodel\PINNs\_multi\_turbine\_wake\_simulation-outputchange

发出前检查下列项目均已包含。路径均相对于项目根目录。

| **文件或目录** | **用途** |
| --- | --- |
| prepare\_pinn\_outputchange.py modify\_pinn\_io.py | 原模型准备、结构改造、训练和预测入口 |
| OutputChange/prepared\_9ms/ | 包含 original\_frozen.keras 等原模型导出文件和准备报告 |
| OutputChange/iochanged\_9ms/ | 包含 untrained.keras、build\_report.json、训练数据模板和结构摘要 |
| OutputChange/project\_config.json | 由接收方填写真实坐标并核对单位 |
| 原仓库代码及 LICENSE 和 README | 保留项目来源、原模型及复现依据 |
| 本指南 | 接收方的操作和数据约定 |

当前待训练模型在 OutputChange/iochanged\_9ms/untrained.keras。模型使用自定义输入连接和标准化层，接收方需要同时保留 modify\_pinn\_io.py；只收到一个 .keras 文件不足以完成后续操作。

建议按任务交接：仿真同学提供机组布置、控制工况和输出标签；负责后续训练的同学配置环境、整理CSV、运行训练并提交测试误差；优化同学确认机组顺序、控制范围、有效风速定义和可接受误差。具体由组内安排，不要求原交付人逐项代填。

项目压缩包不包含收件人电脑上的Conda环境。接收方按下一节准备环境。已完成构建的模型可以直接训练，无须重复运行两个构建脚本。

# 3 接收方准备运行环境

以下步骤针对Windows的Anaconda Prompt。当前已跑通的环境为Python 3.10.21、TensorFlow 2.16.1、TF-Keras 2.16.0。脚本按CPU方式运行。

## 3 1 创建或检查环境

已有相同环境时直接激活。需要新建时执行以下三条命令。

conda create -n pinn-multi python=3.10 -y
conda activate pinn-multi
python -m pip install "tensorflow==2.16.1" "tf-keras==2.16.0"

检查版本，TensorFlow应为2.16.1，TF-Keras应为2.16.0。Python保持3.10系列。

python -c "import sys,tensorflow as tf,tf\_keras as k; print(sys.version.split()[0],tf.\_\_version\_\_,k.\_\_version\_\_)"

本次训练入口只需上述环境及其自动安装的依赖。使用脚本内的 tf\_keras 加载模型；继续运行本次脚本即可，不需要启动原仓库的完整训练程序或为了本次入口安装原 requirements.txt 的全部依赖。

## 3 2 进入解压后的项目根目录

把下面路径替换成自己的解压位置。根目录中应能看到 modify\_pinn\_io.py 和 OutputChange 文件夹。文档中的一条命令如因版面自动换行，执行时仍作为同一条命令复制。

cd /d "C:\pinn\_project\PINNs\_multi\_turbine\_wake\_simulation-outputchange"

原报告可能记录交付人电脑的绝对路径，这些记录用于追溯；训练入口会读取当前项目中的相对文件，不需要新建 Ice-d 用户目录。

# 4 仿真与训练同学填写项目配置

目的：让程序在你们三台机组的真实位置提取原网络特征，并统一控制量单位。位置由仿真布置决定，只需为这版固定布置填写一次。

notepad OutputChange\project\_config.json

配置中关键字段如下。将每组null依次替换为机组1、2、3的真实数值，其他说明字段可保留。下面保留null是为了标出待填项，不能直接用于训练。

"turbine\_positions\_m": [
 [null, null, null],
 [null, null, null],
 [null, null, null]
],
"control\_units": {
 "yaw": "deg",
 "pitch": "deg",
 "rotor\_speed": "rpm"
},
"fixed\_inlet\_wind\_speed\_m\_s": 9.0

* 每组位置为 [x,y,z]，单位m，z为轮毂高度。三个位置必须不同，轮毂高度大于0；与仿真使用同一原点，x沿来流方向，y横向，z竖直。
* yaw和pitch可用deg或rad；rotor\_speed可用rpm或rad/s。配置、数据和优化输入必须一致，脚本不会自动把度转换为弧度或把rpm转换为rad/s。
* fixed\_inlet\_wind\_speed\_m\_s填写数据对应的固定入口风速。默认9.0来自所选源模型；这个字段用于记录和一致性检查，不会作为新输入改变预训练风场。换到其他固定来流工况仍需训练验证。
* 同一版训练数据的风向、湍流强度、机型、转子尺寸和机组顺序应一致。若要同时预测不同环境工况，需要另行扩充条件输入。

# 5 仿真同学准备训练数据

每行对应一个有效控制工况，提供九个控制量和该工况的六个真实结果。建议复制 OutputChange/iochanged\_9ms/training\_data\_template.csv 为 cases.csv，填写后保存到项目根目录。使用逗号分隔的UTF-8 CSV。模板只有表头，没有可用于训练的示例结果。

| **字段** | **含义** | **单位** |
| --- | --- | --- |
| yaw1 yaw2 yaw3 | 三台机组各自偏航角 | 与配置的yaw一致 |
| pitch1 pitch2 pitch3 | 三台机组各自桨距角 | 与配置的pitch一致 |
| rotor\_speed1 rotor\_speed2 rotor\_speed3 | 三台机组各自转速大小 | 与配置的rotor\_speed一致 |
| P1 P2 P3 | 机组1 2 3分别的功率 | W |
| Ueff1 Ueff2 Ueff3 | 机组1 2 3分别的转子盘有效风速 | m/s |

要求使用的完整表头如下。数据读取按列名对应；优化传入向量的顺序则严格按下一节约定。

yaw1,pitch1,rotor\_speed1,yaw2,pitch2,rotor\_speed2,yaw3,pitch3,rotor\_speed3,P1,P2,P3,Ueff1,Ueff2,Ueff3

九维控制向量顺序固定为 yaw1、pitch1、rotor\_speed1、yaw2、pitch2、rotor\_speed2、yaw3、pitch3、rotor\_speed3。六维输出顺序固定为 P1、P2、P3、Ueff1、Ueff2、Ueff3。整个项目采用同一机组编号。

## 5 1 输出标签的约定

功率必须是W。仿真结果如为kW，应乘以1000；如为MW，应乘以1000000。真实停机工况的P可以为0，失败或未收敛的仿真结果不能用0代替。当前脚本要求P非负、Ueff大于0，所有字段均为有限数值。

Ueff的计算方法由仿真和优化同学共同确认，并随数据说明记录采样区域、流速方向与平均方法。必须提供转子盘有效风速标签；当前脚本不会从流场自动积分生成Ueff，风机中心单点风速也不能直接当作盘有效风速。

## 5 2 数据覆盖与环境条件

工况需覆盖准备优化的控制范围，包含控制量的变化和组合。某个角度或转速始终不变时，无法检验模型对它的控制作用。不能把缺失控制量填0后当作完整训练数据。

脚本要求至少5组不同的九维控制组合，才能划分训练、验证和测试；这是程序的划分下限，不代表5组数据足以支撑九维优化。样本数量和覆盖程度由组内结合仿真成本与误差结果安排。

本版仅支持固定来流环境。若CSV中的 wind\_speed、wind\_direction 或 turbulence\_intensity 等环境列发生变化，脚本会报错；不要通过删除列名掩盖不同工况。之前只有风速、风向、湍流强度和功率的数据，也不能自动补成所需的控制量及Ueff标签。

请随CSV附一份数据说明，注明固定风速、风向、湍流强度、机型与转子尺寸、控制范围、单位、机组编号和Ueff计算约定，便于训练与优化两侧核对。

# 6 训练同学运行训练并检查误差

填写配置并准备 cases.csv 后，在已激活环境的项目根目录执行：

python modify\_pinn\_io.py train --bundle "OutputChange\iochanged\_9ms" --csv "cases.csv"

默认最多200轮，批量大小16，学习率0.0001，并按验证损失提前停止。脚本只更新新增输入连接和新输出层；原有隐藏层权重继续冻结。显式指定 --bundle 可确保训练交付的这一版结构。

按不同控制组合约60%、20%、20%划分训练、验证、测试；重复控制组合会放进同一部分。标准化统计只用训练部分计算，验证部分用于提前停止，测试部分用于最后检查。W和m/s先按训练统计标准化后共同计算训练损失，导出预测恢复为物理单位。

训练成功后会在 OutputChange/iochanged\_9ms 下新增 training\_时间戳 文件夹。以终端显示的实际路径为准。该目录包含：

| **文件** | **接收与验收用途** |
| --- | --- |
| trained.keras | 已训练的模型 |
| config\_used.json | 这次训练实际采用的布置、单位与固定风速 |
| training\_report.json | 训练记录、分组行号、控制范围、六个输出的测试MAE和RMSE、原权重校验记录 |

打开报告查看每台功率误差的W值和每台有效风速误差的m/s值。MAE表示平均绝对误差，RMSE会更突出较大的偏差。允许误差由仿真与优化同学根据项目用途约定；完成训练并不自动代表已经达到优化要求。

还应检查 original\_parameters\_unchanged 为true、constant\_controls\_in\_training中是否有计划优化却未变化的变量，以及 negative\_test\_output\_count。线性输出没有强制非负约束；出现负功率或负有效风速时应核查数据与拟合效果。优化提出的最终控制方案建议再用仿真或实验复核。

训练完成后交给优化侧：trained.keras、config\_used.json、training\_report.json、modify\_pinn\_io.py，以及数据说明。保留原训练目录和待训练模型，便于复现。

# 7 优化同学怎样调用

本节在模型完成训练并确认误差后使用。优化侧提供九个控制量，位置由训练时保存的配置固定。输出为六个数，前三个是W，后三个是m/s。总功率可在优化程序中计算为P1加P2加P3。

## 7 1 批量预测

建立 predict\_cases.csv，只需九个控制列，使用相同名称、顺序和单位。在项目根目录执行：

python modify\_pinn\_io.py predict --bundle "OutputChange\iochanged\_9ms" --csv "predict\_cases.csv" --output "predictions.csv"

此命令使用该构建目录中最新完成的训练结果。predictions.csv包含九个控制量和六个预测量。输出文件已存在时，请换一个新文件名，脚本会避免覆盖。指定某次训练时，可用 --run 替换 --bundle，并填写该次 training\_时间戳 目录。

## 7 2 在优化程序内调用

将下面的run\_dir改为实际训练目录；在同一Python进程中加载一次模型，之后反复调用 predict\_case(q)。保留 modify\_pinn\_io.py，并先注册其中的自定义层。

from pathlib import Path
import numpy as np
import modify\_pinn\_io as io

tf, keras, \*classes = io.tensorflow\_components()
run\_dir = Path(
 r"OutputChange\iochanged\_9ms\training\_实际时间戳"
)
config, positions = io.validate\_config(run\_dir / "config\_used.json")
model = keras.models.load\_model(
 str(run\_dir / "trained.keras"), compile=False
)

def predict\_case(q):
 controls = np.asarray(q, dtype=np.float32).reshape(1, 9)
 inputs = io.inputs\_for(controls, positions)
 return model(inputs, training=False).numpy()[0]

q按本指南的九维顺序传入；返回值前3项对应P1至P3，后3项对应Ueff1至Ueff3。该函数提供预测，控制边界、约束和异常处理由优化程序实现。以报告中的训练控制范围和已验证条件设置搜索范围；即使单个变量位于范围内，也需要关注组合工况的覆盖程度。

预测使用 config\_used.json 中的机组位置和单位。训练完成后单独改全局 project\_config.json，不会自动改变已训练模型的适用布置或单位。若布置、机型或来流环境改变，应重新准备对应数据并训练验证。

# 8 常见问题

**出现弃用WARNING：**当前已通过的运行中，这类旧接口提示没有阻止操作。是否成功以末尾的[OK]、保存路径和报告为准；出现[ERROR]时保留完整报错末尾。

**坐标仍为null：**由仿真同学填写真实机组位置，不能沿用检查时的测试坐标；同时确认轮毂高度和坐标系。

**CSV缺少列或存在空白：**对照15列表头补充真实值，Ueff和控制量需要实际数据来源，不能用占位数凑齐。

**控制量不变化或独立工况不足：**补充能覆盖待优化变量的工况；固定变量的作用无法由当前样本验证。

**环境列随工况变化：**先整理固定环境的数据子集，或另行改造条件输入后再训练。固定入口风速与配置不一致时，应核对单位和工况记录。

**找不到训练模型：**当前压缩包交付的是untrained.keras，先完成数据训练。只运行构建命令不会生成trained.keras。

**直接加载时提示自定义层未知：**使用本指南的调用方法，先运行 io.tensorflow\_components()，再用返回的keras加载。不要混用默认tf.keras与本次tf\_keras接口。

**重复运行构建后目录多出后缀：**程序会保留旧目录并生成iochanged\_9ms\_2等新目录。本指南按已交付的iochanged\_9ms操作；需要换版本时，明确调整--bundle路径。

# 9 交接记录

本次已完成的范围为原预训练PINN隐藏层冻结、九个控制输入接入、六个目标输出改造及运行一致性检查。坐标与单位确认、真实数据准备、训练、误差验收和优化结果复核由后续接收任务继续完成。

原项目来源：quest-lab-iisc / PINNs\_multi\_turbine\_wake\_simulation。压缩包保留原作者的代码、模型及LICENSE。

https://github.com/quest-lab-iisc/PINNs\_multi\_turbine\_wake\_simulation
