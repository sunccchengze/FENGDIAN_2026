PINN 三个风况输入扩展：操作与交接说明
日期：2026-10-19

一、你现在要做什么

1. 把本包中的 modify_pinn_wind_io.py 放进原项目根目录：
   C:\Users\Ice-d\Desktop\pinnmodel\PINNs_multi_turbine_wake_simulation-outputchange
   与 modify_pinn_io.py、prepare_pinn_outputchange.py 放在同一层。

2. 在 Anaconda Prompt 中执行：

   conda activate pinn-multi
   cd /d "C:\Users\Ice-d\Desktop\pinnmodel\PINNs_multi_turbine_wake_simulation-outputchange"
   python modify_pinn_wind_io.py

   沿用已经跑通的环境：Python 3.10、TensorFlow 2.16.1、tf-keras 2.16.0。
   不需要重新安装环境。新脚本默认使用 CPU。

3. 等末尾出现 [OK] Checks passed，并确认终端给出的保存目录。
   默认新目录为 OutputChange\wind_iochanged_9ms。
   新配置为 OutputChange\wind_project_config.json。

现在只需做到这里。不需要为了让构建通过，编造机位或训练数据。
构建只加载原模型、扩展输入输出、运行结构检查和保存待训练模型。
出现弃用 WARNING 不一定是失败；出现 [ERROR] 时保留末尾完整日志。
如果需要继续协助检查，请提供末尾日志。

二、这次改了什么，为什么要改

原版本每次只知道九个机组控制量，无法区分不同入口风况。
新版每次接收三个风况量，然后接收原来的九个控制量。
优化侧仍然只调整九个控制量；风况由环境给定。

外部输入为12个物理量，顺序严格固定：
ambient_wind_speed_m_s, ambient_wind_direction_rad, turbulence_intensity,
yaw1, pitch1, rotor_speed1,
yaw2, pitch2, rotor_speed2,
yaw3, pitch3, rotor_speed3

图内自动把风向转换成 sin/cos，所以第一隐藏层实际接收13个新增数值。
调用方只传12个物理量，不要自己多塞一列 sin/cos。
三台机位仍通过单独的位置输入提供，但一版训练与预测使用同一固定布局。

输出仍为：P1, P2, P3, Ueff1, Ueff2, Ueff3。
前三个单位W，后三个单位m/s。机组顺序始终固定。

原隐藏层3,087,200个参数继续冻结；复用全部六个原特征分支。
新增输入连接9,100个参数，新输出18,006个参数，合计27,106个参数参加训练。
没有新增隐藏神经网络。原坐标缩放也继续复用。
可训练参数量少，不表示计算耗时按相同比例减少。

原九输入脚本、原配置及旧模型目录继续保留。
重复构建时会生成 wind_iochanged_9ms_2 等新目录，避免覆盖。
本包不带项目预训练权重；会读取你原项目中已有的：
OutputChange\prepared_9ms\original_frozen.keras

三、现在把哪些东西交给同学

构建成功后，把本说明放进项目根目录，压缩整个项目文件夹交接。
请保留新脚本、wind_iochanged_9ms模型目录、wind_project_config.json，
以及原项目代码、原权重、旧版本和 LICENSE。

先由优化与仿真同学核对以下约定，再准备新数据、训练：

（1）新版控制单位统一为 rad、rad、rad/s。
优化侧文档推荐的就是这一套单位。与旧版默认 deg、deg、rpm 不同。
旧角度转新版：rad = deg * pi / 180。
旧转速转新版：rad/s = rpm * 2*pi / 60。
不能只改配置里的单位文字而不转换数值。

（2）风向约定必须核对。
本脚本定义为风吹向哪里：0沿固定坐标+x，pi/2沿+y，从上方看逆时针为正。
这不是气象上的风从哪里来。如果数据使用来向、顺时针角度或另一零点，
先按实际坐标关系换算，不能直接把旧角度原样填入新列。
偏航角填相对来流的失配角；风向变化后须重新计算失配角。
传入执行器已施加的桨距、转速和偏航运行点，而非未经执行器处理的策略动作。

（3）机位和坐标。
在 wind_project_config.json 中填三台机真实的[x,y,z]，单位m，z为轮毂高度。
坐标沿用原模型原点及零风向参考轴：x沿零风向来流，y横向，z向上。
图内按每个工况的风向，把固定机位旋转到随来流对齐的坐标系。
不需要先把配置中的固定机位按风向旋转，否则会重复旋转。
风向改变也不能重新排列输出里的机组编号。
这一步只是统一坐标语义，不代表原四机9m/s风场自动变成可信的三机新风场。

（4）输出与其他固定条件。
确认P是机械功率还是电功率，三台一致；Ueff要有统一的转子盘等效定义，
不能直接用轮毂中心一个点的风速代替。标签和风况须对应相同统计时间尺度。
本版预测准静态或工况平均响应，没有尾流传播延迟等动态状态。
机型、叶轮尺寸、布局、空气密度及入口剖面在一版数据中保持固定。
请在配置及数据说明里补齐这些元数据，不能悄悄混用不同条件。

四、仿真侧后续提供什么数据

构建目录中的 training_data_template.csv 只有表头，没有伪造的示例标签。
将其复制为项目根目录下的 cases_wind.csv，用真实或有明确物理依据的结果填写。
每行18列：三个风况量＋九个控制量＋六个输出。

完整表头为一行：
ambient_wind_speed_m_s,ambient_wind_direction_rad,turbulence_intensity,yaw1,pitch1,rotor_speed1,yaw2,pitch2,rotor_speed2,yaw3,pitch3,rotor_speed3,P1,P2,P3,Ueff1,Ueff2,Ueff3

CSV须为UTF-8、英文逗号分隔，不得缺列、空白或自行增减列。
风速为m/s；风向和控制角度为rad；转速为rad/s；TI为0~1的小数，10%填0.10。
本接口要求入口风速>0、转速>=0、P>=0、Ueff>0，所有值有限。
真实停机P=0可保留，失败或未收敛仿真不能填0冒充有效结果。
不要把缺少的控制量或Ueff填零来凑齐表格。

数据要覆盖风速、风向、TI和控制量的变化及其组合。
某个条件恒定时，即使训练成功，也不能宣称学会了该条件变化的作用。
程序要求至少5组不同完整工况，仅为划分数据的下限，不代表样本足够。
原来只有风况和功率、没有九个控制量和Ueff的数据不能直接用于本版训练。
若合成标签源本来就不响应风向、TI或布局，增加输入后仍无法学到这些物理作用。

五、拿到数据以后，负责训练的同学执行

先填写 wind_project_config.json 的真实坐标，并完成上面的单位和定义核对。
在项目根目录执行下面一条完整命令：

python modify_pinn_wind_io.py train --bundle "OutputChange\wind_iochanged_9ms" --csv "cases_wind.csv" --label-source simulation

label-source须据实选择：simulation为仿真数据，experiment为实验，
synthetic_test为纯软件联调用的合成测试数据。这个标记会写入训练报告。
如果实际构建目录有_2等后缀，--bundle必须改成终端显示的实际目录。

默认最多200轮、batch16、学习率0.0001，验证损失连续30轮未改善会提前停止。
首次训练包含计算图编译，第一轮可能明显慢于后续轮次。
只训练新增27,106个参数。原主干冻结；标准化只使用训练部分。
重复完整工况会放进同一部分，约按60/20/20划分训练、验证和测试。
训练采用有标签的监督迁移，没有运行原PINN的RANS/k-epsilon残差训练。

训练目录为 wind_iochanged_9ms\training_时间戳，包含：
trained.keras：训练模型；config_used.json：训练实际配置快照；
training_report.json：来源、划分、标准化、输入范围、原权重校验、六输出MAE/RMSE等。

查看 original_parameters_unchanged、constant_inputs_in_training、负输出计数，
并分别查看每台功率的W误差和每台Ueff的m/s误差。误差验收标准由组内约定。
随机划分测试误差不等于已经证明能推广到全新风况；要额外检查未用于选模的
风况、联合控制变化和物理响应。优化给出的最终方案仍应有独立仿真/实验复核。
线性输出未强制非负；负功率/负Ueff不能未经检查直接交给优化使用。
如果冻结主干达不到精度，应先报告结果，再讨论训练范围、数据或微调方案。

六、训练并验收后怎样预测

复制 prediction_data_template.csv，填入12个物理输入，保存为 predict_wind.csv。
在项目根目录执行：

python modify_pinn_wind_io.py predict --bundle "OutputChange\wind_iochanged_9ms" --csv "predict_wind.csv" --output "predictions_wind.csv"

默认使用该构建目录里最新完成的训练。可以用 --run 替换 --bundle，指定某次
training_时间戳目录。输出文件已经存在时必须换新文件名，脚本不会覆盖。
预测使用 config_used.json 的布局，单独改全局配置不会改动已训练模型的布置。
超出训练范围会提示外推；范围内也不代表所有输入组合都已充分验证。

优化程序内调用示例（在项目根目录运行，改成实际训练目录）：

from pathlib import Path
import numpy as np
import modify_pinn_wind_io as io

tf, keras, *_ = io.tensorflow_components()
run = Path(r"OutputChange\wind_iochanged_9ms\training_实际时间戳")
config, positions = io.validate_config(run / "config_used.json")
model = keras.models.load_model(str(run / "trained.keras"), compile=False)

def predict_case(wind_speed, wind_direction_rad, ti, controls_rad):
    # controls_rad是按机组交错的9维向量，转速单位rad/s。
    raw = np.asarray([[wind_speed, wind_direction_rad, ti, *controls_rad]])
    return model(io.inputs_for(raw, positions), training=False).numpy()[0]

先注册本脚本的自定义层，再用返回的keras加载；在同一进程中只加载一次。
返回值顺序仍为P1/P2/P3/Ueff1/Ueff2/Ueff3。不要加载旧版九输入模型。
该函数负责预测；控制约束、异常值处理及搜索范围由优化程序负责。

七、构建成功可以证明什么

能够证明原隐藏参数被保留和冻结、输入作用路径可达、风向编码和坐标变换
符合本接口、临时检查更新被恢复、模型保存重载一致。
检查里使用的探测位置和随机数不是你们的实际布局或物理训练数据。
构建成功不代表新增部分已经学会风况与控制作用，也不代表物理预测精度达标。
原模型来源：quest-lab-iisc/PINNs_multi_turbine_wake_simulation。
交接时请继续保留原项目代码、权重和LICENSE。
