<!-- markitdown-mirror: source="尾流PINN论文2_Gafoor2026_PhysFluids38-055108_多机尾流PINN_doi10.1063-5.0322331.pdf" sha256="2c8989ca25ff" generated="2026-09-21" | 只读镜像，正文由 microsoft/markitdown 自动转换，以同目录原文件为准；重新生成：python3 tools/markitdown_sync.py -->

RESEARCH ARTICLE | MAY 04 2026
Multi-turbine turbulent wake simulation using physics-
informed neural networks
Azhar Gafoor CTP ; Sumanth Kumar Boya ; Rishi Jinka ; Abhineet Gupta ;
Deepak N Subramani
Physics of Fluids 38, 055108 (2026)
https://doi.org/10.1063/5.0322331
 
View Export
Online Citation
Articles You May Be Interested In
A physics-informed neural network for turbulent wake simulations behind wind turbines
Physics of Fluids (January 2025)
Characterization and classification of offshore wind profiles via a shape-based cluster analysis framework
Physics of Fluids (July 2025)
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
Multi-turbine turbulent wake simulation
using physics-informed neural networks
Cite as: Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331
. .
Submitted: 12 January 2026 Accepted: 6 April 2026
Published Online: 4 May 2026
Azhar Gafoor CTP,1,a) Sumanth Kumar Boya,1 Rishi Jinka,1 Abhineet Gupta,2
and Deepak N Subramani1
AFFILIATIONS
1Department of Computational and Data Sciences, Indian Institute of Science, Bangalore, Karnataka 560012, India
2Shell India Markets Pvt Ltd., Bangalore, Karnataka 560103, India
a)Author to whom correspondence should be addressed: azharctp@iisc.ac.in
ABSTRACT
In real-world fluid dynamics, turbulence is prevalent, from swirling coffee in a cup to galaxy formation. Physics-informed neural networks
(PINNs) are pivotal in scientific machine learning and have been applied to engineering turbulence problems; however, they encounter
challenges due to the chaotic and computationally intense nature of turbulence simulations. We introduce a PINN model for simulating
turbulent wakes in multi-turbine configurations using a hybrid physics-data training strategy. Our method integrates data losses with
boundary and partial differential equation losses, as formulated by the 2-equation k−e turbulence model. Using sparse data for a single
flow variable restricted to a plane, the model simulated flow variables in the three-dimensional domain, showing excellent agreement with
the reference (shear stress transport k–x numerical solver) in various scenarios. Training data are viewed as simulated observational data
on a coarse grid, 50�coarser than what the numerical solver requires. A transfer learning strategy is implemented to accelerate training in
new cases, achieving 7:5�faster speed with only one-fourth of the data compared to training from scratch. Our results indicate that the
hybrid training method for PINNs can be successfully applied in practical scenarios with limited sensory data to create neural surrogates for
multi-turbine wind farms.
Published under an exclusive license by AIP Publishing. https://doi.org/10.1063/5.0322331
I. INTRODUCTION Simulation (DNS),1 which explicitly resolves all turbulent temporal
As wind energy becomes increasingly crucial for sustainable and spatial scales but becomes computationally infeasible at high
power generation, optimizing wind farm layouts and turbine perfor- Reynolds numbers. To obtain more practical formulations, turbulence
mance requires accurate prediction of turbulent wake interactions closure strategies are employed. Large Eddy Simulation (LES)2 explic-
between multiple turbines. The complex wake structures that form itly resolves the large, energy-containing eddies and represents the
behind wind turbines significantly affect downstream power genera- remaining unresolved subgrid-scale (SGS) motions through an SGS
tion, structural loads, and overall farm efficiency. Understanding and closure model; the near-wall region in LES can be treated as wall-
predicting these wake interactions is fundamental to advance wind resolved or wall-modeled, contingent on the Reynolds number and
energy technology and maximize renewable energy output. the available grid resolution. The Reynolds-Averaged Navier–Stokes
The underlying physics of turbulent flows, governed by the (RANS) equations3 further decrease computational demands by solv-
Navier–Stokes (NS) equations, represents a challenging problem in ing for time-averaged (or ensemble-averaged) flow fields, with all tur-
physics with far-reaching implications for weather forecasting, aircraft bulent fluctuations accounted for through closure models. RANS thus
design, ocean current prediction, and renewable energy systems. constitutes a practical balance between computational expense and
These partial differential equations form the foundation of modern predictive accuracy, and it is therefore the dominant methodology in
fluid dynamics. The chaotic nature of turbulence, combined with the complex industrial simulations.4–6 These flow problems are typically
non-linearity of the governing equations, presents formidable chal- solved over discretized domains using finite difference, finite volume,
lenges for developing accurate and efficient simulation methodologies. finite element, or spectral methods.
Traditionally, the Navier–Stokes equations have been tackled Nevertheless, conventional numerical approaches face significant
numerically using direct approaches such as Direct Numerical limitations. DNS and LES require very fine spatial discretization to
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-1
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
resolve the full range of turbulent length scales and very small time initial condition (IC) residuals enforced at the initial time. By integrat-
steps to capture temporal dynamics, which leads to extremely large ing PDE residuals with standard data-driven loss components, PINNs
computational meshes and prohibitive costs at high Reynolds num- alleviate the need for extensive simulation data. Moreover, they
bers. Even RANS models, though less expensive, still necessitate high employ automatic differentiation26 for computing PDE residuals,
near-wall grid resolution and iterative solution of coupled nonlinear removing the requirement for complex mesh generation typical of
PDEs, which becomes expensive for complex geometries. Recent traditional solvers. The ability of neural networks to assimilate various
advances in neural networks and massively parallel training on fidelity measurements alongside physical constraints makes PINNs
Graphics Processing Units (GPUs) have created new opportunities in particularly useful when high-quality data are scarce, but some experi-
scientific machine learning (SciML), facilitating the construction of mental measurements are available.14 Despite these strengths, PINNs
neural surrogate models for fluid simulation applications. GPU accel- face well-documented challenges when applied to stiff, multi-scale
eration has also been incorporated into traditional CFD solvers. fluid systems such as high-Reynolds-number turbulence, including
Notable examples are AFiD7 and CaNS8 for incompressible flows, gradient pathologies and optimization instability.27,28
STREAmS9 and URANOS10 for compressible turbulent flows, and Raissi et al.25 initially demonstrated the capability of PINNs to
FluTAS11 for multiphase simulations. While these GPU-accelerated simulate fluid dynamics with minimal data for standard test cases.
CFD solvers substantially decrease wall-clock time, several core limi- Advancements followed with two-dimensional laminar flow solvers
tations remain. Communication overhead across GPU nodes is still a for airfoil shapes,29 and Navier–Stokes Flow nets,30 a turbulent flow
major bottleneck, and GPU-accelerated solvers continue to share the solver for the Navier–Stokes equations. Promising outcomes have
inherent restrictions of conventional CFD: they depend on structured been achieved in turbulent scenarios, including inverse solvers with
or unstructured mesh generation for each new geometry, and these PINN models adopting RANS formulations,31 and NVIDIA SimNet’s
approaches must also re-solve the governing equations from the use in conjugate heat transfer problems.32 Recent studies have pre-
beginning whenever the flow configuration, boundary conditions, or sented PINN-based surrogate models for turbulent flow33 and RANS-
geometric parameters change, requiring full re-initialization and itera- PINN schemes for estimating unknown turbulence equation compo-
tive convergence.12 This makes systematic parametric studies (e.g., nents.34 In the three-dimensional setting, Biswas and Anand35
examining the impact of varying inlet conditions, turbulence intensi- employed PINNs to model laminar flows governed by the Navier–
ties, or geometric parameters across many configurations) and real- Stokes equations, demonstrating that PINNs can address complex 3D
time deployment computationally infeasible.13,14 fluid dynamics without conventional numerical schemes. More
A widely used class of SciML frameworks for solving partial dif- recently, Hu et al.36 proposed a hybrid strategy that combines a
ferential equations (PDEs) is operator-learning methods, including physics-informed neural network with a characteristic-based split
DeepONet,15 the Fourier Neural Operator,16 and Representation algorithm, reducing labeled data requirements, memory consump-
Equivalent Neural Operators.17 These methods, which learn mappings tion, and computational time, while enhancing accuracy and conver-
between function spaces, have demonstrated improved generalization gence for 3D incompressible Navier–Stokes flows. PINNs have
in PDE solution tasks by employing novel architectures that map spa- likewise been applied to reconstruction problems, including the
tial coordinates, geometry, and operating conditions to flow field vari- reconstruction of the 3D wind field around a building model in a
ables. Nevertheless, the operator-learning methods often demand wind tunnel using a PINN framework incorporating a zero-equation
large amounts of high-quality data for training, with their performance turbulence closure,37 the reconstruction of turbulent velocity and
significantly declining in data-scarce situations, due to which these pressure fields from under-resolved, noisy particle trajectory measure-
approaches often face limitations when applied to high-dimensional ments,38 and the development of a physics-informed variational auto-
turbulent flows, particularly for three-dimensional and multi-source- encoder for reconstructing 3D turbulent wall-bounded flow fields
term PDEs.18 While the operator-learning methods have seen limited from sparse planar measurements.39 The results show that the PINN
adoption specifically for wake modeling and wind power forecasting framework provides an effective approach for simulating and recon-
applications, numerous data-driven neural network models have been structing flow fields in engineering applications. PINNs have also
proposed for these tasks. Examples include models based on Artificial been applied to various prediction tasks in wind farm flows.
Neural Networks (ANN)19–21 or a combination of Proper Orthogonal Specifically, NS equations in combination with sensory data are used
Decomposition (POD) with Long Short-Term Memory networks,22 in a PINN framework to estimate freestream wind fields in front of
and convolutional neural networks (CNNs).23 These data-driven wind turbines.40,41 Another study proposes a data-independent PINN
approaches rely heavily on large, high-quality training datasets, which surrogate to simulate three-dimensional wind turbine wakes based on
are often difficult to obtain in real-world settings, or generating such the k–e turbulence model.42 Different PINN variants are compared by
simulation data are resource-intensive, requiring significant computa- Cobelli et al.43 for reconstructing two-dimensional velocity field for a
tional power and time, often running traditional numerical methods wind turbine with sparse data and NS equations. For wake field pre-
on multiple-core systems for extended periods24 which limits the dictions, a PINN framework integrating two-dimensional NS equa-
broader adoption of these methods in engineering applications. tions, sensory data and actuator disk model is proposed to simulate
Physics-Informed Neural Networks (PINNs) provide a promis- the entire wake field.44 Wang et al.45 studied the dynamic nature of
ing alternative through a loss function based on PDE-residuals for wake using the PINN framework with a moving average window
semi-supervised or unsupervised training.25 In the standard PINN technique. An improved PINN model with a cosine annealing algo-
formulation, the total loss comprises multiple terms: the PDE residual rithm and dynamic weight strategy, together with two-dimensional
evaluated at the collocation points, boundary condition (BC) residuals NS equations, sparse data, and the actuator disk model, is proposed
enforced at domain boundaries, and for time-dependent problems, for dynamic wake field prediction.46 In general, the application of
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-2
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids                                                                 A   R  T   I C  L  E             p  u bs.aip.org/aip/pof
PINNs in engineering flows is still in a preliminary stage, typically  The equations for incompressible steady RANS with k and e transport
limited to laminar flows,47,48 or benchmark examples in turbulent  equations in Cartesian coordinates are expressed in the form of
flows  or  turbulent  flows  in  a  two-dimensional  regime.49–51  We  implicit partial differential equations as follows
acknowledge that the modern literature on PINNs is extensive. As
@u i¼0;
such, we restrict our focus to models for turbulent wake simulation,  Continuity:fðu;xÞ¼ (1a)
|     |     |     | c   | @x  |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
excluding other significant works in related sectors. i"   !#
T h e   c u r r e n t  s t a t e -o f- t h e - a r t  R A N S - b a s e d   P I N N  m o d e l  d e m on - @ u u 1 @ p @ @ u @ u
.4 2  Momentum:f ðu;xÞ¼ i jþ − � iþ j
strate s  e x c e ll e n t  p e r f o r m a n c e   w i t h  s in gl e  t u r b i n e s Ex pa n d i n g  P IN N   m @ q @ @ @ @
|     |     |     | x j | x i | x j x | j x i |     |     |
| --- | --- | --- | --- | --- | ----- | ----- | --- | --- |
methods to study interactions between multiple wind turbine wakes is
@s
a crucial advancement. Simulating multiple turbine wakes involves  ij−S
|     |     |     | þ   | ¼0; |     |     | (1b)  |     |
| --- | --- | --- | --- | --- | --- | --- | ----- | --- |
complex challenges, such as wake interactions, diverse atmospheric  @x i
j
conditions, and the need to model wake recovery and meandering  " � � #
|     |     |     | @ku | @   | � @k |     |     |     |
| --- | --- | --- | --- | --- | ---- | --- | --- | --- |
that influence downstream turbines. These challenges remain largely  k−transport:f ðu;xÞ¼ j− �þ t þe¼0;
|     |     | k   |     |     |     | −P k |     |     |
| --- | --- | --- | --- | --- | --- | ---- | --- | --- |
unaddressed in the current literature on PINNs.52–54 Furthermore,  @x @x r @x
|     |     |     | j   | j   | k j |     |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
key questions remain on whether complex turbulence can be simu- (1c)
|     |     |     |     | "�  |     | #   |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
lated without observational or simulation guidance during training. �
|     |     |     | @eu | @   | �   | @e  |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
In   t h is  w o r k ,  w e  i m p le m e n t  a   h y b r i d   tr a in i n g  s t r a t e g y   w i t h i n  t h e  e−transport:fe ðu;xÞ¼ j− �þ t
|     |     |     | @x  | @x  | r   | @x  |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
PINN  f r a m e w o r k   to   s im u l ate   t u r b u l e n t   w a k e   in t e r a c t i o n s   a c r o s s  a   j j e j
grid of wind turbines. Our approach integrates simulated sparse
|     |     |     |     | e   | e2  |     |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
pseudo-measurement data obtained from a RANS simulation using a  −C P þC −Se ¼0; (1d)
|     |     |     |     | 1e k k | 2e k |     |     |     |
| --- | --- | --- | --- | ------ | ---- | --- | --- | --- |
traditional computational fluid dynamics (CFD) solver. The main
|     | where  | u¼ðu;v;w;p;k;eÞ | represents  |     | the  solution  | field  | and  |     |
| --- | ------ | --------------- | ----------- | --- | -------------- | ------ | ---- | --- |
contributions of this work are:
|     | x¼ðx;y;zÞ | denotes the spatial coordinates within the domain X.  |     |     |     |     |     |     |
| --- | --------- | ----------------------------------------------------- | --- | --- | --- | --- | --- | --- |
(1) Development of a PINN model to solve RANS equations for  Here, u;v;w are the three-dimensional velocity components, p is the
simulating turbulent flow in multi-turbine wind farm configu-
|     | mean pressure, �is the kinematic viscosity, � |     |     |     | t  is the turbulent viscos- |     |     |     |
| --- | --------------------------------------------- | --- | --- | --- | --------------------------- | --- | --- | --- |
rations using a hybrid physics-data training strategy.
|     | ity, P k  | is the production of turbulent kinetic energy (TKE), S |     |     |     |     | i  is the  |  12 September 2026 13:03:32 |
| --- | --------- | ------------------------------------------------------ | --- | --- | --- | --- | ---------- | --------------------------- |
(2) Comprehensive documentation of the challenges and solutions
momentum source/sink term in the i direction, and Se is the source/
for training RANS simulations with PDE-residual loss terms in
sink term for dissipation rate.
complex multi-turbine domains.
The undefined terms in Eq. (1) are defined as follows:
(3) Open-source release of code, model architecture, optimized    !
h y p e r p a ra m e t e r s ,  a n d  t r a in e d  m o d e ls   t o  e n a ble direct applica- 1 @ u @ u
|     |     | Reynolds−stress:s |     | ¼−� | iþ  | j ; | (2a)  |     |
| --- | --- | ----------------- | --- | --- | --- | --- | ----- | --- |
ti o n  t o   m u lti - t u r b i n e  w i n d  f a rm  s i m u l a t io n s . ij t @ @
|     |     |     |     | 2   | x j | x i |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
(4) Application of transfer learning to accelerate PINN training for
turbulent wind turbine wake flows under varying atmospheric  k2
|             |     | Turbulentviscosity:� |     | ¼Cl | ;   |     | (2b)  |     |
| ----------- | --- | -------------------- | --- | --- | --- | --- | ----- | --- |
| conditions. |     |                      | t   | e   |     |     |       |     |
|             |     |                      |     |     | !   |     |       |     |
In the remainder of the paper, we first discuss the development  @u @u @u
|     |     | Prod:ofTKE:P | ¼�  | iþ   | j     | i:  | (2c)  |     |
| --- | --- | ------------ | --- | ---- | ----- | --- | ----- | --- |
|     |     |              | k   | t @x | @x @x |     |       |     |
of the PINN model for simulating wake turbulence in multi-turbine  j i j
arrays (Sec. II). After that, the results of the model development and
simulation results are presented, including the calculation of the
power output (Sec. III). The issues faced while training, computa- For the three-dimensional turbulent wake simulation around wind
tional time, and transfer learning strategy to reduce time are pre- turbines under neutral atmospheric conditions, the constant values in
sented in the discussion (Sec. IV). Finally, a summary with future  Eqs. (1) and (2) are Cl ¼0:033, r ¼1:0, r e ¼1:3, C 1e ¼1:176, and
k
directions concludes the paper (Sec. V). C ¼1:92, determined by regression fits of observation data.56
2e
The PINN framework employs gradient descent to optimize
II. DEVELOPMENT OF THE PHYSICS INFORMED
over a loss landscape comprising PDE, boundary, and data losses.
NEURAL NETWORK
Here, the loss landscape denotes the behavior of the objective function
A. Reynolds averaged Navier–Stokes equations with
with respect to the network parameters, particularly its non-convex
an actuator disk wind turbine model
geometry, extended flat regions, and numerous local minima and sad-
For the multi-turbine turbulent wake simulation, we choose the  dle points. In contrast to conventional CFD solvers, which at each
Reynolds Averaged Navier–Stokes (RANS) equations with an actua- iteration resolve a well-posed linear system, a PINN jointly minimizes
tor disk model for the wind turbine. The RANS equations are time-  a composite loss that includes PDE residuals, boundary condition
averaged equations designed to simulate turbulent fluid flows. They  penalties, and data misfit terms. This multi-objective setup creates
several optimization challenges: gradients from different loss compo-
are formulated by decomposing turbulent flow variables into time-
averaged and fluctuating components, followed by time averaging,  nents may conflict, driving parameter updates in opposing directions;
resulting in a Reynolds-stress term s ij . This stress term is modeled  large differences in the magnitudes of the loss terms can lead to severe
using the k−e turbulence closure model, which provides transport  ill-conditioning; and stiffness induced by multi-scale near-wall phe-
equations for turbulent kinetic energy (k) and dissipation rate (e).55  nomena, where flow fields change rapidly over very short distances,
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331                                                                                                                                                                   38, 055108-3
Published under an exclusive license by AIP Publishing

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
can generate extremely steep loss gradients that are difficult for stan- S ¼− 1 qC u2; (5)
dard gradient descent methods to navigate.28,57–59 To address this, we i 2 T
incorporate wall functions directly into the loss function. In standard
where u represents the flow velocity measured at an upstream location
industrial flow applications, wall functions are employed to obtain
equal to four turbine diameters, which is used as the reference for cal-
accurate computational fluid dynamics simulations at a reduced com-
culating the thrust coefficient (Sec. IIIA). The negative sign indicates
putational expense.60–62 These functions enforce a physically consis-
that the thrust is applied to the incoming flow, making S a momen-
i
tent near-wall velocity profile, thereby mitigating the scale separation tum sink. The standard k−eRANS closure model, while predicting
between the wall and the freestream. By constraining the solution to
the disk’s presence, often overestimates some flow variables. Thus, an
adhere to the expected mean flow behavior in the region adjacent to additional term in the e-transport equation [Eq. (1d)] is added to
the wall, the wall function acts as a regularizer for the optimization
address this overestimation. This additional source term Se captures
landscape and steers the model away from nonphysical local minima
the energy transfer rates from large to small-scale turbulence, influ-
(see the Appendix D).
enced by the production range scale and the dissipation rate time-
In the RANS governing equations, the wind turbine is repre- scale,64,65 and is expressed as follows:
sented by the actuator disk model, employing source terms S
i
and Se.
t T h h e e fl m ow om a e c n ro tu ss m t h s e o u a r c c t e u a t t e o rm r d ( i S sk i ) ’ s i n re E g q io . n ( . 1 b T ) h a ru p s p t l i ( e T s ) t h a r n u d s t p f o o w rc e e r s ( o P n ) Se ¼C 4eq P k k 2 ; (6)
equations are
where C 4e is set at 0.37 based on experimental data,65 P k is the produc-
T¼ 1 qC A u2; (3) tion of turbulent kinetic energy, and k is the turbulent kinetic energy.
2 T d 0 In the current PINN formulation, the source terms are computed
1 dynamically at every training iteration. Rather than prescribing the
P¼ qC A u3; (4)
2 P d 0 velocity in the source term as a fixed input, it is obtained from the
PINN’s own prediction of the velocity field at the specified upstream
where C is the thrust coefficient, C is the power coefficient, A is
T P d location relative to the turbine rotor. At each iteration, the network first
the disk area, and u is the upstream velocity. C is a dimensionless
0 T infers this upstream velocity, which is then used to evaluate the source
coefficient representing the axial force exerted by the turbine on the
term and incorporate it into the residual of the momentum equation
incoming flow, and C is the ratio of the power extracted by the tur- P within the actuator disk region. This guarantees that the source term
bine to the wind energy. Manufacturers supply the thrust and power
evolves in step with the predicted flow field over the course of training,
coefficients for modeling the turbine’s components, such as blades
enabling the network to converge to the solution in which turbine forc-
and the generator. Although the actuator disk model lacks geometric
ing and the surrounding velocity field are intrinsically linked.
details of the turbine, it effectively represents the mean wake impact
and accurately calculates the power output in wind farm simula-
tions.63 In this study, the thrust force from Eq. (3) is averaged over B. PINN model and loss function
the turbine area and distributed along the streamwise direction using In the physics-informed neural network method (PINN; Fig. 1),
the source term a parameterized neural model H is trained to approximate the
FIG. 1. Schematic of a PINN model for three-dimensional RANS simulation. The PINN model is a fully connected feed-forward dense neural network (NN) shown in the
blue enclosure. The loss calculation through automatic differentiation (AD) is visualized as dotted connections in the red enclosure. Three losses are calculated (i) partial dif-
ferential equation (PDE) residual loss, (ii) boundary condition (BC) loss, and (iii) data loss.
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-4
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids                                                                 A   R  T   I C  L  E             p  u bs.aip.org/aip/pof
functional relationship between the input domain X and the solution  C. Implementation
domain U, i.e., H:x�h7!u, where h denotes the set of trainable  TensorFlow software package66 is used to implement the PINN
weights and biases. We consider H to be a fully connected feed-
model described above. The model has three inputs, six outputs, and
forward neural network (enclosed in the blue box of Fig. 1), predicts
other internal layers as shown in Fig. 1. The implementation in the
| the output (u^;^v;w^;^p;^ |     | k;^e) for a domain point in (x;y;z). Thus,  |     |     |     |     |     |     |     |     |     |     |
| ------------------------- | --- | ------------------------------------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
present paper is built inspired by a recent development of a single-
u^ðx;hÞis the approximate solution of the PDEs under consideration.
turbine PINN model.67 Table I presents the important hyperpara-
The partial derivatives in the governing equations (e.g., @u^=@x or
meters such as neurons per layer and sampling points that are deter-
higher-order terms) are computed using automatic differentiation.
mined through extensive experiments (see Appendix C for ablation
The value of turbulent viscosity [Eq. (2b)] or momentum source term
study). The Swish activation function is used for three hidden layers
[Eq. (5)] are computed directly from the model outputs. Boundary
with 700 neurons each, and the six pre-output layer with 500 neu-
conditions are enforced as soft constraints through dedicated BC loss
rons,68 while Rectified Linear Unit (ReLU) is used for the last output
terms included in the composite training objective, consistent with
nodes representing turbulent kinetic energy (k) and dissipation rate
the standard PINN formulation. For Dirichlet boundary conditions,  (e) to avoid negative values; other outputs do not have an activation
the boundary data are directly compared with the output of the  function. Parameter optimization involves the Adam optimizer with
PINN,  bypassing  automatic  differentiation.  Neumann  conditions  adaptive gradient descent and momentum,69 starting with an expo-
require automatic differentiation to compute losses. The data losses
nentially decaying learning rate of 0.0001 at a decay rate of 0.9 and a
are formed by comparing the model prediction with any measure-
decay step of 5000. Parameters are initialized using the Glorot uni-
ments or simulations at specific spatial locations. As the problem con-
|     |     |     |     |     |     |     | form  | initializer.70  | Mini-Batch  | training  | is  used  | for  the  three-  |
| --- | --- | --- | --- | --- | --- | --- | ----- | --------------- | ----------- | --------- | --------- | ----------------- |
sidered is steady-state, initial condition loss terms are not included in
dimensional wake simulation due to the high collocation points, per-
the PINN formulation.
formed on an NVIDIA RTX A6000 GPU. The code, the model archi-
The parameters (h) of the neural network H are learned by min-
tecture, and the trained weights have been released on GitHub with a
imizing a loss function L
|     |     |     | PINN  that comprises the PDE-residual loss,  |     |     |     | Zenodo DOI.71 |     |     |     |     |     |
| --- | --- | --- | -------------------------------------------- | --- | --- | --- | ------------- | --- | --- | --- | --- | --- |
boundary loss, and data loss, i.e.,
III. THREE-DIMENSIONAL TURBULENT FLOW
|     | L   | ¼a L | þaL | þa  | L ; | (7a)  |     |     |     |     |     |     |
| --- | --- | ---- | --- | --- | --- | ----- | --- | --- | --- | --- | --- | --- |
PINN b boundary r residual d data SIMULATION ON A GRID OF WIND TURBINES
|     |     |     | 2   |     | 3   |     |     |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
 12 September 2026 13:03:32
1 XNbp T h e   P I N N   m o d e l  i s u t i l i z e d   t o   fo re c a s t  t h e w a k e  g en e ra t e d   a n d
|     |     | L ¼ | 4 ðBðu^ðx | ÞÞ−bÞ25; |     | (7b)  |     |     |     |     |     |     |
| --- | --- | --- | --------- | -------- | --- | ----- | --- | --- | --- | --- | --- | --- |
boundary i the p o w e r   o u tp u t  in   a   m u l t i - t u r b i n e  w i n d   f a rm  g r id .  W a k e s   o c c u r
N bp
i¼1 downstream due to the obstruction created by the wind turbine as it
|     |     | "   |     |     |     | #   |     |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
XNc disrupts the incoming airflow. All turbines are represented using an
1
L ¼ a ðf Þ2þa ðf Þ2þa ðf Þ2þa ðfe Þ2 ; (7c)  actuator disk model72,73 and incorporated into the k−eRANS model
|     | residual | N 1 | c 2 m | 3 k | 4   |     |     |     |     |     |     |     |
| --- | -------- | --- | ----- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
c i¼1 as a source term (Sec. IIA). The domain and experimental setup are
|     |     |     | 2   |     | 3   |     |     |              |                             |                           |                         |                                |
| --- | --- | --- | --- | --- | --- | --- | --- | ------------ | --------------------------- | ------------------------- | ----------------------- | ------------------------------ |
|     |     |     |     |     |     |     | d i | s cu s s e d |   i n  Se c .  II I A .   F | o r   t h e   pu r p o se |   o f  n u m e r ic a l |  s im u l a ti o n s,   t h e  |
XNdp
|     |     |     | 1 4 ðMðu^ðxÞÞ−mÞ25: |     |     |     |     |     |     |     |     |     |
| --- | --- | --- | ------------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
L ¼ (7d)  w a k e  i s   c o m p u te d   in   a   g r i d   c o n fi g u ra ti o n   w i th   fo u r   tu rb i n e s  h a v i n g
|     |     | data N |     | i   |     |     |     |     |     |     |     |     |
| --- | --- | ------ | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
dp i¼1 specifications of the Sexbierum HOLEC WPS 30/3 Wind Turbine.
Section IIIC discussed the hybrid training strategy for the PINN
Here, the boundary conditions are expressed as BðuðxÞÞ¼b on
model, followed by the simulations in Sec. IIID.
| x2@ | X, and measurement data as MðuðxÞÞ¼m on x2@ |     |     |     |     | X,  |     |     |     |     |     |     |
| --- | ------------------------------------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|     | b                                           |     |     |     |     | m   |     |     |     |     |     |     |
where @ X is the boundary of the domain, b is the boundary condi-
b
A. Domain and boundary conditions
| tion value, @ | m   | X denotes the spatial locations where measurement/  |     |     |     |     |     |     |     |     |     |     |
| ------------- | --- | --------------------------------------------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
Figure 2 shows the schematic of the domain used for simulations
| simulation data (m) is available. a |     |     | is the weighting coefficient for  |     |     |     |     |     |     |     |     |     |
| ----------------------------------- | --- | --- | --------------------------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
b  with a rectangular grid pattern. We perform simulations on a rectan-
| boundary losses, a |     | is the weighting coefficient for residual losses, a |     |     |     |     |     |     |     |     |     |     |
| ------------------ | --- | --------------------------------------------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|                    |     | r                                                   |     |     |     | d   |     |     |     |     |     |     |
is the weighting coefficient for data losses, and a are the weighting  gular  grid  pattern  of  wind  turbines.  Wind  turbines  (WTs)  are
1−4
coefficients assigned to the residuals of each governing PDE. The val-
ues of these coefficients are fixed based on hyperparameter sensitivity  TABLE I. Hyperparameters used for wind turbine wake simulation.
| experiments  |     | (See  Appendix  | A).  The  | coefficients  | a and  | a are  |     |     |     |     |     |     |
| ------------ | --- | --------------- | --------- | ------------- | ------ | ------ | --- | --- | --- | --- | --- | --- |
|              |     |                 |           |               | b      | d      |     |     |     |     |     |     |
weighed 10�more compared to the coefficient a Neurons (hidden layers) 700
r  and the coefficients
| a 1−4  are given weights in the ratio 100:10:1:1. N |     |     |     |                              | c  represents the  |     |     |                         |               |     |                   |     |
| --------------------------------------------------- | --- | --- | --- | ---------------------------- | ------------------ | --- | --- | ----------------------- | ------------- | --- | ----------------- | --- |
|                                                     |     |     |     |                              |                    |     |     | Neurons (output layer)  |               |     | 500               |     |
| total count of location points within the domain, N |     |     |     |                              | denotes the total  |     |     |                         |               |     |                   |     |
|                                                     |     |     |     |                              | bp                 |     |     |                         | Learning rate |     | 0.0001            |     |
| number of boundary points and N                     |     |     |     | denotes the total number of  |                    |     |     |                         |               |     |                   |     |
|                                                     |     |     | dp  |                              |                    |     |     | Learning rate scheduler |               |     | Exponential decay |     |
measurement/simulation data points. The boundary loss and data
loss terms are determined using the mean squared error on the pro- Epochs 15000
vided boundary data and measurement/simulation data, respectively.  Optimizer Adam
The PDE-residual loss is calculated as the L2 norm of the residuals at  Trainable-parameters 3090200
training points calculated using automatic differentiation. Since PDE-  Batches 16
residuals are incorporated in the loss function during training, these  Activation function SwishþReLU
models are termed physics-informed. (Convergence of the individual  Initializer Glorot uniform
loss components during training is shown in Appendix B.)
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331                                                                                                                                                                   38, 055108-5
Published under an exclusive license by AIP Publishing

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 2. Schematic of the rectangular grid domain of wind turbines: (a) lateral view, (b) front view, and (c) top view. D is the diameter of the turbine, and H is the hub height.
The boundary conditions used on the domain surfaces are also shown.
modeled according to the specifications of the Sexbierum HOLEC
WPS 30/3 Wind Turbine. The HOLEC WPS 30/3 WT has a diameter
D¼30.1 m and a hub height H¼35 m. The boundary conditions are
set for a free stream wind speed ranging from 7 to 11m/s with a tur-
bulence intensity of 10% at the hub height. The thrust coefficients cor-
responding to these conditions are also used from the thrust curve.
Figure 3 shows the power curve and the thrust coefficient curve of the
HOLEC WPS 30/3 WT. The PINN model relies solely on the thrust
coefficient curve for the training phase, whereas the power curve is
utilized during the post-processing stage. For each simulation, the
PINN model is trained from scratch.
Fully developed inlet profiles are specified at the inlet boundary
for mean velocity [Eq. (8a)], turbulent kinetic energy [Eq. (8b)] and
turbulent dissipation rate [Eq. (8c)] as follows:74
� �
u¼
us
ln
zþz
0 ; (8a)
j z
0
u2
k¼pffisffiffiffiffiffi; (8b)
Cl FIG. 3. Thrust and power coefficient curves of the HOLEC WPS 30/3 WT.
u3
e¼ s ; (8c)
jðzþz Þ
qffiffiffiffi 0 momentum and k−e model equations.75 At the outlet, a provided
where us ¼ s q w is the friction velocity (with s w is the wall shear pressure boundary condition and zero gradients along the stream-
stress, and q is the fluid density), j�0:418 is the von K�arm�an wise direction for other quantities are imposed. At the bottom wall/
constant, z is the height coordinate, and z is the aerodynamic rough- ground, wall functions consistent with the inlet profiles are used to
0
ness height. Inlet profiles [Eq. (8)] are analytical solutions of the specify Dirichlet conditions for velocity, turbulent kinetic energy, and
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-6
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
dissipation rate. Dirichlet conditions are also applied on the top face practices. In the far-wake region, only thrust force and turbulent
to stay consistent with the inlet profiles. The lateral faces in the three- kinetic energy are affected by the turbine, thus necessitating fewer
dimensional domain are provided with symmetry boundary condi- sampling points than in the near-wake region. (Total number of sam-
tions with a zero velocity normal to the face. pled points are discussed in Appendix B. Three-dimensional illustra-
tion in provided in Appendix A.)
B. Sampling of boundary and domain collocation
points for training C. Hybrid physics and data-driven training strategy
For the training of the PINN model, the boundary loss [Eq. (7b)] The nature of the wake generated behind the turbines depends
and PDE-residual loss [Eq. (7c)] are evaluated at points sampled using on the incoming wind. Various methods have been reported to esti-
the grid-based method and the Hammersley method,76,77 respectively. mate the characteristics of the incoming wind in a wind farm,81,82
Figure 4 shows the sectional visualization of the three-dimensional such as using wave wind Light Detection and Ranging (LiDAR),83
computational domain used for the flow simulations. The orange wave Doppler LiDAR,84,85 and anemometer towers.86 These measure-
markers denote the boundary points, while the blue and green ments are mostly restricted to sparse locations, such as line-of-sight
markers represent the domain collocation points used only for evalu- wind observations along the beam path in LiDAR, which prevents the
ating PDE-residual losses. The green regions correspond to the actua- direct reconstruction of the detailed spatiotemporal wind field.87
tor disk zones that model the turbine rotors. The source terms used to Therefore, coupling the sparse data with flow physics is a suitable
model the thrust force are applied in a cylindrical region with a diam- strategy for estimating the complete wind field, and the use of such
eter equal to the turbine diameter (D) and a length of 0.25 times the measurement to improve PINN training is illustrated in this study by
turbine diameter upstream and downstream of the disk.65 The inset using synthetic measurement data drawn from the RANS solution
in Fig. 4 provides an enlarged view of one actuator disk region, where computed by conventional CFD solvers. In this study, the term
the thrust force is normally distributed along the streamwise direc- “sparse data” denotes data that are sparse in three-dimensional space
tion, allowing a seamless calculation of PDE-residual losses by avoid- (available only on a single horizontal plane) and additionally of low
ing a sudden change in the disk region. Downstream of the wind resolution on that plane (i.e., coarsely sampled). A two-dimensional
turbine are two distinct regions: near-wake and far-wake.78 The near- slice extracted from the three-dimensional CFD simulation is com-
wake region, which extends two to four times the turbine diameter bined with the governing PDEs to train the PINN model within our
downstream, features a complex flow influenced by the rotor design hybrid physics–data-driven training strategy. Specifically, the stream-
and the aerodynamics of the blade.79,80 To accurately capture near- wise velocity at the domain points lying on the horizontal plane
wake behavior, the domain collocation points for training are through the turbine center is employed for training. The numerical
increased within a cylindrical volume of length six times the turbine solver with the chosen mesh size produces 193776 grid points on this
diameter and diameter two times the turbine diameter, symmetrically horizontal plane. For PINN training, however, we utilize a signifi-
placed around the disk as indicated by the refined region in Fig. 2 and cantly coarser grid containing only 3876 points, which is 50�fewer
by the dense clustering of blue points near turbines in Fig. 4. This than the grid points used in the numerical solver. The use of a regu-
method is inspired by traditional numerical solver mesh refinement larly spaced, grid-based dataset is not mandatory; a randomly
FIG. 4. Sectional views of the three-
dimensional domain. (i) Orange: bound-
ary points, (ii) blue: domain collocation
points. Dense region indicates the refine-
ment near the turbine, and (iii) green:
actuator disk region. The inset shows an
enlarged view of the region near the actu-
ator disk. The thrust force is distributed
normally along the streamwise direction.
The axes are normalized by the turbine
diameter (D).
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-7
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
TABLE II. RMSE between the simulation from the PINN model and the numerical solver. Normalized velocity and TKE are compared at the inlet, 3D, 6D, 9D, 12D, and 15D
downstream of the turbine in a horizontal plane at the hub height of the wind turbines.
Inlet 3D 6D 9D 12D 15D
Normalized velocity 0.00119 0.00217 0.00207 0.00240 0.00208 0.00182
Normalized TKE 0.00473 0.38926 0.40284 0.48142 0.50201 0.42480
distributed dataset can also be employed during training (see multiple realizations with different random seeds (see Appendix E).
Appendix B for details). Figure 11(a) presents the simulation results The RMSEs for the normalized velocity and TKE at different locations
when observational data are incorporated alongside the PDEs. in horizontal and vertical planes along the height of the hub are
A simulation based on the finite volume method is executed in reported in Tables II and III, respectively. Thus, qualitatively and
Simcenter StarCCMþ88 using the Shear Stress Transport (SST) k−x quantitatively, we see that the developed PINN model is capable of
turbulence model.89 The turbulence model and the mesh size used giving results comparable to the SST k–x model. A study on different
were selected on the basis of related studies to ensure a mesh- turbulence models had concluded that the SST k–x model is an effec-
independent solution.42,90 This simulation data are used as a sensor tive turbulence model for wind turbine simulations.90 Thus, the fact
simulator and ground truth for verification of the PINN model that our PINN model matches well with the simulations of SST k–x
simulations. gives us confidence to deploy a PINN forward simulator as a wake
surrogate for downstream applications.
D. Wake simulations from the trained PINN model In the contour plot (Fig. 5), the wake created by the turbine is
evident from the low-velocity (panel a) and low-pressure (panel c)
Tables II and III and Figs. 5–7 present the main results of the
regions downstream of the turbines. This causes turbulent transport
PINN simulation. The goodness of the PINN simulation is computed
of momentum from the ambient wind into the wake region as seen in
by calculating the error [as Root Mean Squared Error (RMSE)]
the turbulence intensity contour plot (Panel b). The wind turbine gen-
between the PINN simulation and the corresponding StarCCMþ
erates turbulence in addition to that already produced by the terrain,
CFD simulation on two planes.
indicated by the increased turbulence intensity behind the turbine. It
Figure 5 shows the contour plot of the RANS-PINN turbulent
is also evident that the turbulence intensity has a sharp structure
flow simulations (velocity, turbulence intensity and pressure) in hori-
emerging from the disk edges which is an indication of vortex forma-
zontal and vertical planes, passing through the hub of the wind tur-
tion immediately behind the rotor blade tips (marked by numeral I).
bines for the rectangular grid. Figures 6 and 7 show the normalized
Further downstream, a shear layer is formed and encloses the wake
velocity and normalized turbulent kinetic energy profiles in two dif-
(marked by numeral II). The far wake region is also well predicted by
ferent planes at the inlet and different downstream locations (3D, 6D,
the PINN model. It is indicated by the expansion of the shear layer to
9D, 12D, and 15D, where D is the turbine diameter) of the first tur-
the center by turbulent diffusion (marked by numeral III). The axi-
bine along with the simulation from the CFD k–xSST solver for
symmetric nature of the wake seen in the contour plots is a result of
comparison. The flow variables are normalized by the corresponding
the RANS closure being used for the simulations. The RANS turbu-
far-field values from the simulation. The Root Mean Square Error,
lence closure fails to simulate highly transient fine vortex tubes, which
vffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffiffi
u in turn obstruct the development of complex vortex structures, and
RMSE¼
u
t1
XN �
/PINN−/CFD
�
2 ; the simulated vortex tube moves in a straight line without meander-
N i i ing. The pressure jump across the disk is seen from the pressure con-
i¼1
tours (marked by numeral IV), which is also an indication of the
is evaluated, where / represents the normalized flow variable (either thrust force exerted by the turbine on the incoming flow. A higher
velocity or TKE), N is the number of sampling points at a specified pressure jump indicates a larger thrust force.
downstream location, and the superscripts ð�ÞPINN and ð�ÞCFD indicate, Figure 8 shows the comparison of velocity and turbulence inten-
respectively, the prediction of the PINN model and the reference sity between PINN model and CFD solver in a horizontal plane, along
CFD solution obtained with the k–xSST model. These RMSE values with the absolute error map. The velocity magnitude indicates that
are computed for simulations of the PINN model carried out over the PINN model effectively reproduces the wake structures and
TABLE III. RMSE between the simulation from the PINN model and the numerical solver. Normalized velocity and TKE are compared at the inlet, 3D, 6D, 9D, 12D, and 15D
downstream of the turbine in two vertical planes through the center of the wind turbines at 63:5D.
y/D Inlet 3D 6D 9D 12D 15D
Normalized velocity −3.5 0.03227 0.04403 0.04513 0.04740 0.05125 0.05545
3.5 0.03464 0.04803 0.04841 0.04487 0.04956 0.05594
Normalized TKE −3.5 0.02532 0.35919 0.32936 0.49995 0.50344 0.48002
3.5 0.02899 0.40695 0.34970 0.51040 0.48727 0.46044
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-8
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 5. Contours of (a) velocity, (b) turbulence intensity, and (c) pressure in two planes through the center of wind turbines in a rectangular grid for U ¼9m=s: (i) top: hor-
ref
izontal plane and (ii) bottom: vertical plane at y/D¼63:5.
velocity deficits downstream of the turbines, demonstrating close The quantitative comparison shows that the downstream wind speed
agreement with the CFD results. The turbulence intensity exhibits predicted by the model aligns well with the CFD solver in both planes
similar spatial trends, with elevated values observed within the wake and remains within the estimated confidence intervals at most down-
regions. The absolute error maps reveal that the deviations are pri- stream locations, indicating that the PINN surrogate delivers trust-
marily confined to the wake shear layers, where strong velocity gra- worthy predictions with appropriately quantified uncertainty. Figure
dients and turbulence fluctuations occur (Error map in vertical plane 7(a) shows the effectiveness of the hybrid training strategy to employ
is shown in Appendix F). Overall, the PINN model accurately cap- PINN as a forward solver with sparse data availability. For our hybrid
tures the flow physics, particularly the variations in velocity. Figure 9 training strategy, only data for a single flow variable (u) in the hori-
also substantiates the findings, which show the streamlines around zontal plane are used. However, the velocity profiles in the vertical
the wind turbine in horizontal and vertical planes for simulations plane also match well with the CFD solver showing that the PINN
from the PINN model and the CFD solver. Flow variations near the model has learned the dynamics accurately. Figures 6(b) and 7(b)
turbine are well simulated in both planes. Even though no data are show the normalized turbulent kinetic energy at the above-mentioned
used in the vertical plane, contours and streamlines below and above downstream locations in the horizontal and vertical planes, respec-
the turbine [Fig. 9(b)] indicate that the PINN model effectively learns tively. In the near-wake region of the turbines (3D and 9D), the PINN
the physics using the hybrid training strategy. model is able to predict the TKE peaks generated by the tip vortices
Further comparison with the CFD numerical simulation is per- similar to the SST k−x. It is more evident in 9D that it is closer to
formed to validate our PINN model at different downstream locations the turbine. A distorted peak formation is observed close to the second
of the wind turbine at a distance of 3D, 6D, 9D, 12D, and 15D in both row turbine (6D). Further downstream (12D and 15D), the TKE profiles
vertical and horizontal planes through hub of the wind turbines. The exhibit a flatter peak. As expected, slightly larger uncertainty is likewise
profiles at the inlet are also compared. The PINN predictions shown detected in the wake region downstream of the turbines, where the flow
in Figs. 6 and 7 correspond to the ensemble mean obtained from five dynamics exhibit increased complexity. In addition, the RMSE for TKE
independently trained models with different random initializations, reported in Tables II and III appears higher compared to the velocity
while the shaded regions represent the 95% confidence intervals com- components. This discrepancy arises primarily from the modeling
puted from the ensemble predictions, illustrated as shaded bands. inconsistency between the reference CFD solver and our PINN formula-
These confidence intervals provide an estimate of the predictive tion. In our work, the PINN is trained using the k–e turbulence model,
uncertainty of the PINN model. Figures 6(a) and 7(a), respectively, whereas the reference CFD data are generated using the SST k–x model.
show the normalized wind speed as a function of the spanwise direc- These two RANS closures are known to produce systematically different
tion in a horizontal plane and as a function of wall-normal direction TKE distributions, particularly in regions with strong shear, and wake
in a vertical plane through the hub of the wind turbine for the rectan- recovery zones. As a result, even when the velocity fields match closely,
gular grid. The center or hub of the four wind turbines in the rectan- the TKE fields exhibit inherent model-form discrepancies that inflate
gular grid is located at 63.5D in the spanwise direction at 0D and 7D error metrics.89,91,92 Although the TKE is slightly underestimated
in the streamwise direction. The maximum wind speed deficit is between the two columns of the turbines in the far downstream regions,
observed in the direction behind the center of the turbine, as expected. overall, the PINN model provides simulations that are able to predict
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-9
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 6. Comparison of (a) velocity and (b) turbulent kinetic energy predicted by the PINN model with the numerical solver in a horizontal plane at the hub height of the wind
turbines. The PINN mean predictions (solid orange) with 95% confidence intervals (shaded) are shown alongside CFD reference results (blue dots).
the peaks with good precision with the aid of limited velocity E. Power output from the grid
data. Similar results for another grid configuration are discussed in In a wind farm design problem, a quantity of interest is the power
Appendix G. All simulations shown in this section are based on output from each turbine. The power output of the individual turbines
U ref ¼9m=s. Simulations on the rectangular grid for other reference on the grid is calculated using Eq. (4) with the velocity at 3D upstream
velocities are shown in Appendix H. of the turbine and the corresponding power coefficient (Fig. 3). Figure
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-10
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 7. Comparison of (a) velocity and (b) turbulent kinetic energy predicted by PINN model with the numerical solver in a vertical plane through the center of wind turbines.
PINN mean predictions for Row 1 (solid orange) and Row 2 (dashed green) with 95% confidence intervals (shaded) are shown alongside CFD reference results (blue dots).
10(a) shows the power output of turbines placed at different down- outputs predicted by the PINN model and the CFD solver is reported in
stream locations calculated by the velocity predictions of the PINN Table IV. Percentage errors remain under 0.2% for Row 1 turbines
model. Power calculated from the CFD solver is also shown for compar- across all inlet velocities, and under 0.4% for Row 2 turbines, with the
ison. The absolute error and percentage error between the power exception of the 11m/s case, which exhibits a 1.7% error. These results
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-11
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 8. Contours showing comparison of velocity and turbulence intensity between PINN model and CFD solver in a horizontal plane at the hub height of the wind turbines
in a rectangular grid for U ¼9m=s. (a) PINN, (b) CFD, and (c) error map: (i) top: Velocity magnitude and (ii) bottom: turbulence intensity.
ref
FIG. 9. Contours of velocity magnitude along with streamlines near the first wind turbine for simulations from PINN model and CFD solver in (a) horizontal plane and (b) ver-
tical plane for U ¼9m=s.
ref
indicate that the PINN model provides highly accurate predictions of IV. DISCUSSION
power output across the examined operating range. The plots and the A. Issues faced while training with only PDE-residual
error values show that the PINN model is able to give an excellent esti- loss
mate of the power output. A velocity difference of typically 1% can result
Before using measurement data simulated from a CFD solver for
in a power deviation of >2.5% due to the cubic relationship between
training the PINN model, we tried simulating the wake generated on
velocity and power. When normalizing the power output with the values
a grid of turbines without using any simulated measurement data,
of the first turbine, it can be seen that the normalized values of the sec- using only the PDE-residual loss term. However, the simulations of
ond row turbine are almost the same across different inlet velocities the PINN model, shown in Fig. 11(b), indicate that the prediction
[Fig. 10(b)]. This also indicates that the wake simulated by the RANS does not accurately reflect the real world system intended to be mod-
turbulent models at different velocities exhibits a similar nature, giving eled. On close observation, it is evident that the momentum source
further confidence in deploying a PINN model as a forward simulator. term [Eq. (5)] is overestimated, causing a pulling effect on the flow.
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-12
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 10. Comparison of (a) power output
and (b) normalized power output calcu-
lated by the velocity predictions of the
PINN model for wind turbines located at
different downstream locations for differ-
ent inlet velocities. Power output pre-
dicted by the CFD solver is also shown in
(a).
For applications with only a single turbine case, the velocity to calcu- 0.0353, 0.0609, and 0.9836. It is also evident from Fig. 11(d), which
late the source term could be provided with a static upstream value. shows the quantitative comparison of the velocity at different down-
However, in situations where there are turbines downstream of the stream locations in the horizontal plane, that the hybrid training strat-
wake, the velocity will vary until a steady state is reached. Our training egy provides a substantial improvement in the simulations. These
experiments show that the PINN model fails to reach an optimum findings suggest that some kind of regularization or control is needed
where the calculated thrust force achieves a balance with the bound- for the PINN model to successfully simulate the domain with a tur-
ary conditions of the domain, causing an increase in the streamwise bine grid. (The importance of enforcing physical constraints with
velocity upstream of the turbines. Although the contours of pressure, sparse data are further demonstrated in Appendix J.)
spanwise velocity, and wall-normal velocity exhibit a trend close to
the reality, the turbulent flow parameters are simulated very poorly. B. Scalability of the model
To assert the findings, we tried to limit the magnitude of the source
To evaluate the scalability of the proposed PINN-based surrogate
term by clipping the maximum value of the streamwise velocity for
model, we extended our simulation setup from a 4-turbine configura-
the source term calculation. We saw an improvement in the simula-
tion to a more complex 6-turbine layout. The transition to a larger
tions [Fig. 11(c)]. However, the estimated values of source terms
wind farm scenario increases the spatial domain size, the number of
always touch the maximum value. The variation of mean squared val- actuator forcing regions, and the complexity of wake interactions.
ues of the source term and x component of the momentum equation
Despite this added complexity, the model maintained stable training
during the training is shown in Fig. 12. It can be observed that, when
behavior and produced accurate flow-field predictions. It can be
trained only with PDE residuals, the value of the source term varies
observed from the Fig. 13 that the model scales effectively with the
throughout the training, indicating that the model does not reach an
number of turbines. In particular, the increase from 4 to 6 turbines
optimal value for the source term. Whereas the other two training
required only a modest increase in computational cost while preserving
strategies help the model to stabilize the value of the source term after
prediction quality. This indicates that the underlying architecture and
a few training epochs. However, limiting the magnitude of the source
training strategy generalize well to larger multi-turbine configurations.
term affects the model’s ability to minimize the loss in the x-
momentum equation. At the end of the training, the mean squared
C. Training and inference time
values of the source term are 4.0924, 8.4607, and 5.8588 for three
training strategies: (i) hybrid-training (PDE þ Data), (ii) with only We utilize a single NVIDIA RTX A6000 GPU with 48GB of mem-
PDE residuals, and (iii) limit the magnitude of the source term, ory on a dedicated workstation with an Intel Core i9 CPU operating at
respectively. The respective values of the x-momentum equation are 3.70GHz for training the PINN model. We trained the three-
TABLE IV. Absolute and percentage error in power output calculated from the predictions of the PINN model compared to the CFD k–xSST numerical solver for wind tur-
bines located at Row 1 and Row 2 for inlet velocities ranging from 7 to 11m/s. Absolute errors are reported in kW. Percentage error is defined as jPPINN−PCFDj�100, where
PCFD
PPINN and PCFD denotes the PINN and reference CFD power outputs, respectively.
Velocity 7 m/s 8 m/s 9 m/s 10 m/s 11 m/s
Row 1 2 1 2 1 2 1 2 1 2
PPINN (kW) 47.9567 12.3726 71.8642 18.7750 102.2254 28.1674 139.7971 38.7257 182.3285 52.4613
PCFD (kW) 47.9623 12.3594 71.7752 18.7931 102.1894 28.0234 139.8541 38.8612 182.1030 51.6025
Abs. error (kW) 0.0057 0.0132 0.0890 0.0181 0.0361 0.0144 0.0570 0.1355 0.2255 0.8588
% Error 0.0119 0.1068 0.1240 0.0963 0.0353 0.0513 0.0408 0.3487 0.1238 1.6643
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-13
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 11. Contours of velocity in a horizontal plane at the hub height of the wind turbines for three PINN training strategies: (a) hybrid-training (PDEþData), (b) with only
PDE residuals, (c) limiting the magnitude of the source term, and (d) comparison of the velocity predicted by the PINN model with the numerical solver for the three training
strategies.
dimensional wake simulation for a wind turbine grid with about 61600 resolution CFD mesh containing approximately 36 �106 cells, was exe-
sampling points from the domain, which took 2087:1569:90 min. The cuted using 4 active cores. The total solver elapsed time was 104385.74s
total training time for the PINN model reduced to 1018.98min when or 1739.76min. Inference using the PINN model is much faster and
executed on a workstation featuring an NVIDIA RTX PRO 6000 does not need high-performance GPUs. On our desktop with an
Blackwell GPU with 96 GB memory, highlighting the potential of NVIDIA GeForce RTX 2070, line plot simulations with 1000 spatial
emerging GPU technologies to significantly shorten computational points were completed in milliseconds. For contour plots on a 500�
time. The CFD simulations with the StarCCMþsolver were evaluated 500�1 grid, inference took less than 30s. A drawback of current PINN
using a machine equipped with an Intel Xeon processor featuring 16 frameworks, including ours, is the long training time compared to CFD
physical cores operating at 2.49GHz. The simulation, based on a high- solvers. However, advancements like the Physics-informed transformer
FIG. 12. Variation of mean squared val-
ues of (a) source term and (b) x compo-
nent of momentum equation during
model training for three training strate-
gies: (i) hybrid-training (PDEþData), (ii)
with only PDE residuals, and (iii) limiting
the magnitude of the source term.
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-14
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 13. Contours of (a) velocity, (b) turbulence intensity, and (c) pressure in two planes through the center of wind turbines in a rectangular grid of six turbines for
U ¼9m=s: (i) top: horizontal plane and (ii) bottom: vertical plane at y/D¼63:5.
ref
neural operator (PINTO)93 aiming to generalize boundary and initial velocity case, respectively. The other velocity simulations in each test
conditions, might enable models to train once for diverse scenarios. Our case are the pre-trained model in a transfer learning setting. In transfer
PINN models are distinct as they are trained with limited data of one learning for the higher velocity case, U ¼11m=s simulations are
ref
flow variable and incorporate PDE residual loss, unlike most data- obtained by fine-tuning the pre-trained lower velocity models
driven neural models that need comprehensive data from the entire (U¼7−10m=s), and for the lower velocity case, U ¼7m=s simu-
ref
domain and have difficulty predicting non-included variables. Thus, lations are obtained by fine-tuning the pre-trained higher velocity mod-
with sparse velocity data from simulated LiDAR or anemometer towers, els (U¼8−11m=s). Reference simulations are used to evaluate the
our PINN model provides deep insights into the flow across the domain. quality of the simulation produced by transfer learning. We observe that
Neural networks facilitate transfer learning, using a pre-trained model on performing 2000 epochs of fine-tuning in this transfer learning task,
for one flow scenario as a basis for another, reducing computational the simulation agrees with the reference simulations. Also, for transfer
requirements during training, as shown next. learning, only one-fourth of the simulated measurement data points are
required to reach convergence compared to the model trained from
D. Transfer learning for other inlet conditions scratch. Figure 14 shows the streamwise velocity along the centerline at
the hub height for the model, after transfer learning, compared to the
Even though the training time of the hybrid PINN model is less
reference (dashed lines) and pre-trained models (solid lines). The
than that of the PDE-only model, it is still higher than the run time of
a state-of-the-art numerical solver. Hence, we adopt the transfer markers denote the simulation after transfer learning, with values indi-
learning strategy to reduce the training time for new turbulent flow cating the reference velocity of the pre-trained model. To simulate the
situations. While transfer learning has been explored in PINNs frame- case with different velocity and turbulence intensity from a pretrained
work,94,95 the present work demonstrates its effectiveness in the spe- model with different conditions, we used models trained with
cific setting of multi-turbine wake interactions, where the domain U¼7 and11 m/s at a turbulence intensity of 10% as the pre-trained
involves multiple actuator disk sources, and sparse measurement data models. The target is to fine-tune these models to simulate a case with
under varying inflow and atmospheric stability conditions. The U¼9m/s at turbulence intensities of 6% and 8%. Similar to the first
approach reduces computational requirements when adapting to new scenario, 2000 epochs of fine-tuning turned out to be effective. Figure
operating conditions without retraining from scratch. In transfer 15 shows the streamwise velocity along the centerline at the hub height
learning, a pre-trained model checkpoint is used as the starting point for the model, after transfer learning, compared to the reference (dashed
for training models for new tasks/situations. For three-dimensional lines) and pre-trained models (solid lines). A comparison of the velocity
wake simulation on a grid of wind turbines, changing the reference in a horizontal plane at hub height at different downstream locations for
velocity (U ) or turbulence intensity (TI ) changes the boundary the two scenarios is shown in Appendix I. The results show good agree-
ref ref
conditions, which affects the thrust and power output, thereby requir- ment between the reference and the simulations from the fine-tuned
ing a new training of the PINN model. model. Fine-tuning took 274:6061:43 min compared to 2087:1569:90
In the experiments, we show (i) how a higher-velocity test case can min for the training from scratch. We see that the PINN model with
be quickly simulated from a pre-trained lower-velocity PINN model transfer learning converged 7:5�faster compared to the model trained
and vice versa while maintaining a constant turbulence intensity across from scratch with lesser training data. While the transfer learning shows
the simulations and (ii) how a test case with different velocity and turbu- promising results for different inlet velocities and turbulence intensities,
lence intensity can be simulated from a pretrained model with different its performance under changes in turbine configuration currently
conditions. First, the PINN model is trained with U ¼7−11 m/s at requires substantially more fine-tuning and higher training epochs,
ref
a turbulence intensity of 10% for 15000 epochs. The 11 and 7m/s simu- which limits its practical effectiveness. Regardless of the fact that an
lations are used as references for the higher velocity case and the lower end-to-end PINN training is data-hungry and computationally
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-15
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 14. Velocity along the streamwise centerline at hub height of the wind turbines simulated by the transfer learning strategy. (a) Higher velocity (U ¼11m=s) simula-
ref
tion from pre-trained lower velocity (U ¼7;8;9;and10m=s) model, (b) lower velocity (U ¼7m=s) simulation from pre-trained higher velocity
ref ref
(U ¼8;9;10;and11m=s) model. The dashed line is the target in each case, starting from the pre-trained model denoted by solid lines, whose velocity corresponds to
ref
the marker color. Markers denote the simulation after transfer learning, and the marker value is the U of the pre-trained model.
ref
confined to a single plane in the three-dimensional domain, can easily
be replaced with sensory measurements, thus avoiding the need for a
forward numerical solver during the training phase. A transfer learning
strategy is developed to reduce the training time for PINN model in
new atmospheric flow configurations when starting from a pre-trained
PINN model with a different flow configuration. Our results demon-
strate the possibility of using PINNs as a framework for simulating tur-
bulent wake in multi-turbine settings.
Although the proposed framework does not currently exceed the
computational efficiency of state-of-the-art spectral solvers, it pro-
vides a compelling proof of concept: turbulence in engineering appli-
cation domain can be modeled using physics-informed neural
networks, yielding continuous, mesh-free solutions unconstrained by
FIG. 15. Velocity along the streamwise centerline at hub height of the wind tur- conventional discretization. The present study employs a down-
bines simulated by the transfer learning strategy. U¼9m/s at turbulence intensi- sampled CFD dataset as a proxy for sparse measurements; future
ties of 6% and 8% simulations from a pre-trained model with U¼7and11m/s at work should assess model performance under truly sparse, noisy real-
turbulence intensity of 10%. The dashed line is the target in each case, starting world sensor data such as those obtainable from dual-Doppler LiDAR
from the pre-trained model denoted by solid lines. Markers denote the simulation
deployments. With future advances in wider generalizations and
after transfer learning.
newer PINN architectures, our results will serve as a benchmark.
expensive, adopting approaches like transfer learning combined with ACKNOWLEDGMENTS
the utility of PINN models to perform fast inferences makes them a via-
ble option in real-world simulations even with sparse data availability. We thank all members of the QUEST Lab at IISc for useful
Although PINNs may fall short of the accuracy and efficiency of high- discussions. The authors are grateful for the Prime Minister’s
order CFD solvers for conventional forward problems and are therefore Research Fellowship (PMRF) from the Ministry of Education to
unlikely to fully supplant existing CFD, they nevertheless offer a realistic Azhar Gafoor CTP. This research is partially supported by research
alternative when dealing with problems with partial information. grants from the Ministry of Earth Sciences (MoES/36/OOIS/Extra/
84/2022) and Shell India Markets Private Limited.
V. CONCLUSION
A physics-informed neural network model using hybrid PDE and AUTHOR DECLARATIONS
data-based training is developed to simulate turbulent wake on a grid
Conflict of Interest
of wind turbines using the RANS formulation with the 2-equation k−
e turbulence closure model. The training strategy uses a mixture of The authors have no conflicts to disclose.
PDE-residual losses, boundary condition losses, and measurement/sim-
Author Contributions
ulation data losses. The simulations from the trained PINN model
showed excellent consistency with the reference for different atmo- Azhar Gafoor CTP: Conceptualization (equal); Data curation (equal);
spheric inlet flow scenarios. The use of simulated observation data were Formal analysis (equal); Investigation (equal); Methodology (equal);
only on a sparse grid for a single flow variable from the numerical Software (equal); Validation (equal); Visualization (equal); Writing – orig-
solver. Nevertheless, the PINN model was able to predict all variables inal draft (equal). Sumanth Kumar Boya: Investigation (supporting);
accurately for the entire domain. In addition, these data, which are Methodology (supporting); Software (supporting); Visualization
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-16
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids                                                                 A   R  T   I C  L  E             p  u bs.aip.org/aip/pof
(supporting). Rishi Jinka: Investigation (supporting); Methodology (sup- PDE overly influencing the network’s learning, causing the effects of
porting). Abhineet Gupta: Software (supporting); Validation (equal).  other equations to be ignored or boundary/data losses to overshadow
Deepak  N.  Subramani:  Conceptualization  (equal);  Formal  analysis  residual losses, or vice versa, resulting in the model becoming stuck in
(equal); Methodology (equal); Project administration (equal); Supervision  some local minima. To resolve this imbalance, a weighting strategy is
(equal); Validation (equal); Writing – review & editing (equal). implemented to assign equal importance to all equations and bound-
ary/data losses throughout the training process. The RMSEs of the nor-
malized velocity and TKE at different locations in the vertical plane
DATA AVAILABILITY
along the height of the hub for varying weights for different losses and
The data that support the findings of this study are openly avail- equations are reported in Table V. It can be observed how varying the
able  in  GitHub  and  Zenodo  at  https://github.com/quest-lab-iisc/  weights affects the model performance. On weighing the coefficients
PINNs_multi_turbine_wake_simulation, Ref. 71 a and a 10�more compared to the residual coefficient, a, and giv-
|     |     |     |                                                            | b  d  |     |     | r      |
| --- | --- | --- | ---------------------------------------------------------- | ----- | --- | --- | ------ |
|     |     |     | ing weights in the ratio 100:10:1:1 for the coefficients a |       |     |     | , the  |
1−4
PINN model showed overall better accuracy.
APPENDIX A: WEIGHTS FOR DIFFERENT LOSSES
Unlike conventional numerical methods that update parameters
APPENDIX B: TRAINING LOSS CONVERGENCE
| by  sequentially  | iterating  through  | discretized  equations,  | Physics-  |     |     |     |     |
| ----------------- | ------------------- | ------------------------ | --------- | --- | --- | --- | --- |
Informed Neural Networks (PINNs) process all governing PDEs and  Figure 16 shows the evolution of the individual loss compo-
other supervised components (boundary and data losses) simulta- nents during training, including the boundary/data loss, total PDE
neously during training. This approach can lead to a single, dominant  residual, continuity equation, three-momentum equations, and the
TABLE V. RMSE between the simulation from the PINN model and the numerical solver for varying weights for different losses and equations. Normalized velocity and TKE
are compared at the inlet, 3D, 6D, 9D, 12D, and 15D downstream of the turbine in two vertical planes through the center of the wind turbines at 63:5D. Bold and underlined
values denote the lowest RMSE in each row.
|     | Boundary/Data | a , a | 1   | 1   | 1   | 10  | 10  |
| --- | ------------- | ----- | --- | --- | --- | --- | --- |
|     |               | b d   |     |     |     |     |     |
|     | Residual      | a     | 1   | 1   | 1   | 1   | 1   |
r  12 September 2026 13:03:32
a
|     | Continuity equation | 1   | 1   | 10  | 100 | 100 | 100 |
| --- | ------------------- | --- | --- | --- | --- | --- | --- |
a
|     | Momentum equation    | 2   | 1   | 1   | 10  | 10  | 10  |
| --- | -------------------- | --- | --- | --- | --- | --- | --- |
|     | k-transport equation | a 3 | 1   | 1   | 1   | 1   | 10  |
|     | e-transport equation | a   | 1   | 1   | 1   | 1   | 1   |
4
Inlet Normalized velocity 23.5 0.03014 0.03024 0.05261 0.02938 0.03734
|     |                | 3.5  | 0.02990 | 0.03402 | 0.05222 | 0.02924 | 0.03777 |
| --- | -------------- | ---- | ------- | ------- | ------- | ------- | ------- |
|     | Normalized TKE | 23.5 | 0.03714 | 0.11416 | 0.02648 | 0.02940 | 0.02295 |
|     |                | 3.5  | 0.03350 | 0.14641 | 0.03712 | 0.03343 | 0.03091 |
23.5
3D Normalized velocity 0.03654 0.04191 0.04721 0.03030 0.05440
|     |                | 3.5  | 0.03981 | 0.03961 | 0.04209 | 0.03416 | 0.05374 |
| --- | -------------- | ---- | ------- | ------- | ------- | ------- | ------- |
|     | Normalized TKE | 23.5 | 0.66795 | 0.69725 | 0.42517 | 0.38178 | 0.67481 |
|     |                | 3.5  | 0.60667 | 0.63488 | 0.41722 | 0.36582 | 0.71469 |
6D Normalized velocity 23.5 0.03411 0.03402 0.04873 0.03068 0.04911
|     |                | 3.5  | 0.03646 | 0.04086 | 0.03872 | 0.03533 | 0.05663 |
| --- | -------------- | ---- | ------- | ------- | ------- | ------- | ------- |
|     | Normalized TKE | 23.5 | 0.65482 | 0.68376 | 0.41633 | 0.31367 | 0.63133 |
|     |                | 3.5  | 0.63976 | 0.65793 | 0.37699 | 0.30461 | 0.69591 |
9D Normalized velocity 23.5 0.04314 0.04633 0.05566 0.03272 0.05222
|     |     | 3.5 | 0.05611 | 0.04811 | 0.04662 | 0.03949 | 0.06143 |
| --- | --- | --- | ------- | ------- | ------- | ------- | ------- |
23.5
|     | Normalized TKE |     | 0.71357 | 0.76935 | 0.66766 | 0.47368 | 0.74408 |
| --- | -------------- | --- | ------- | ------- | ------- | ------- | ------- |
|     |                | 3.5 | 0.73791 | 0.73638 | 0.69578 | 0.49894 | 0.77638 |
12D Normalized velocity 23.5 0.03471 0.03762 0.05241 0.03627 0.05315
|     |                | 3.5  | 0.03758 | 0.03931 | 0.04415 | 0.04101 | 0.05890 |
| --- | -------------- | ---- | ------- | ------- | ------- | ------- | ------- |
|     | Normalized TKE | 23.5 | 0.64450 | 0.65795 | 0.54598 | 0.45351 | 0.62171 |
|     |                | 3.5  | 0.63942 | 0.60322 | 0.52795 | 0.44819 | 0.62052 |
15D Normalized velocity 23.5 0.03798 0.0256 0.05308 0.04158 0.05564
|     |                | 3.5  | 0.03117 | 0.03594 | 0.04750 | 0.04572 | 0.06009 |
| --- | -------------- | ---- | ------- | ------- | ------- | ------- | ------- |
|     | Normalized TKE | 23.5 | 0.55896 | 0.53499 | 0.50429 | 0.44909 | 0.51731 |
|     |                | 3.5  | 0.54574 | 0.50217 | 0.49306 | 0.43706 | 0.50616 |
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331                                                                                                                                                                 38, 055108-17
Published under an exclusive license by AIP Publishing

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 16. Convergence of the individual loss components during training, including boundary/data loss, PDE residual, continuity, momentum, k-transport, and e-transport
equations.
transport equations for turbulent kinetic energy and dissipation domain, with a higher density near the actuator disk region,
rate. All components exhibit a consistent monotonic decrease over denoted by the green region. The PINN training accuracy depends
the course of training, indicating stable optimization and balanced on the number of sampled points where the losses are calculated.
enforcement of the governing equations and boundary conditions. The total number of collocation points depends on the base size
ðbÞ. The sampling is done sequentially: first, the entire domain is
APPENDIX C: ABLATIONS sampled with b�104 points, then a refined region is sampled with
b�103 points around the turbine center, and finally, b�103
The ablation studies are carried out for simulations in a
points are sampled for the actuator disk region. During each sam-
domain with a rectangular grid of turbines, with U ¼10m=s and
ref pling stage, points sampled in the former stage in the overlapping
a turbulence intensity of 10%.
regions are omitted. Thus, the entire collocation sample points will
be less than b�ð104þ103þ103Þ. Table VII lists the RMSE
1. Model parameters between the simulation from the PINN model and the numerical
Table VI lists the RMSE between the simulation from the solver for different numbers of collocation points. A significant
PINN model and the numerical solver for different numbers of gain in accuracy is observed when the base size is increased from 2
model parameters, along with the training time. The parameters to 3. Even though the mean RMSE value reduces further on
are varied by changing the number of neurons in the three com- increasing the base size to 4, it comes at a higher computational
mon hidden layers from 600 to 800. The model with 3090200 cost, especially when the model needs to be trained for higher
parameters is chosen for subsequent experiments because it offers epochs. Therefore, a base size of 3 is chosen as the optimal as it
improved performance over smaller models while providing a offers a good balance between computational cost and accuracy.
practical balance between computational cost and accuracy com-
pared with larger models. 3. Number of data points
Table VIII summarizes RMSE between the PINN solution and
2. Number of collocation points the numerical solver for different numbers of sampled data points
The collocation points for the three-dimensional domain are and sampling strategies. The simulation was initiated with a higher
shown in Figs. 4 and 19. The blue region represents the entire number of sampled points, and the progression of error with the
TABLE VI. RMSE between the simulation from the PINN model and the numerical solver for different numbers of model parameters. Normalized velocity is compared at the
inlet, 3D, 6D, 9D, 12D, and 15D downstream of the turbine in a horizontal plane at the hub height of the wind turbines. The mean of RMSE is also listed.
Parameters Time/1000 epochs (mins) Inlet 3D 6D 9D 12D 15D Mean
3690800 150.81 0.00131 0.00108 0.00103 0.00079 0.00044 0.00056 0.00087
3090200 139.14 0.00119 0.00124 0.00120 0.00079 0.00051 0.00059 0.00092
2529600 116.09 0.00093 0.00173 0.00167 0.00228 0.00135 0.00108 0.00151
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-18
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
TABLE VII. RMSE between the simulation from the PINN model and the numerical solver for different numbers of collocation points. Normalized velocity is compared at the
inlet, 3D, 6D, 9D, 12D, and 15D downstream of the turbine in a horizontal plane at the hub height of the wind turbines. The mean of RMSE is also listed. Higher base size
denotes higher points.
Base size Time/1000 epochs (mins) Inlet 3D 6D 9D 12D 15D Mean
4 156.53 0.00128 0.00102 0.00098 0.00080 0.00044 0.00050 0.00084
3 139.14 0.00119 0.00124 0.00120 0.00079 0.00051 0.00059 0.00092
2 123.89 0.00108 0.00202 0.00215 0.00279 0.00128 0.00086 0.00170
TABLE VIII. RMSE between the simulation from the PINN model and the numerical solver for different numbers of sampled data points and sampling strategies. Normalized
velocity is compared at the inlet, 3D, 6D, 9D, 12D, and 15D downstream of the turbine in a horizontal plane at the hub height of the wind turbines. The mean of RMSE is also
listed.
Method No. of data points Inlet 3D 6D 9D 12D 15D Mean
Random 8000 0.00097 0.00115 0.00096 0.00084 0.00047 0.00052 0.00082
4000 0.00152 0.00117 0.00111 0.00077 0.00049 0.00055 0.00094
2000 0.00107 0.00272 0.00295 0.00349 0.00153 0.00101 0.00213
Grid-based 3876 0.00119 0.00124 0.00120 0.00079 0.00051 0.00059 0.00092
1938 0.00133 0.00222 0.00305 0.00334 0.00129 0.00089 0.00202
Random % 3873 (�2%) 0.00113 0.00111 0.00090 0.00149 0.00045 0.00049 0.00093
1923 (�1%) 0.00137 0.00287 0.00319 0.00338 0.00154 0.00096 0.00222
reduction of the number of data points was observed. The mean dimensional turbulent channel flow benchmark. This channel flow
RMSE of the simulation with 8000 randomly sampled data points is configuration is a standard validation problem for turbulent flow
0.00082. Reducing the number by 50% to 4000 yields a mean RMSE solvers, with DNS reference data available over a range of Reynolds
of 0.00094, which is approximately only 15% worse. Upon further numbers.96
reducing the number of sampled points to 2000, a significant
increase (�126%) in the mean RMSE value is observed. A similar a. Problem setup
trend in RMSE is observed when a different sampling strategy, grid-
The flow between two flat plates separated by a distance of 2h
based, is used. In this method, a structured coarse grid of data points
is driven by a constant pressure gradient in the streamwise direc-
is sampled from the fine mesh-grid by skipping intermediate grid
tion. The simulation is performed on half the channel height,
points in an orderly fashion (see Appendix B). A slightly better
exploiting the symmetry of the fully developed flow (Fig. 17). The
mean RMSE (0.00092) is obtained using the grid-based approach
(3876 data points) compared to random sampling. Furthermore,
friction Reynolds number is defined as Res ¼ush=�, and the study
instead of randomly sampling from the entire available data, a more
is conducted at Res ¼180. Setting us ¼1 m/s and h¼1 m, the
kinematic viscosity is �¼1=180 m2/s, and the constant pressure
targeted approach is used to ensure that the sampled dataset main-
gradient is @p=@x¼−1Pa/m for density q¼1 kg/m3.
tains a uniform distribution of points across the domain. In this
The PINN model solves the RANS equations with the k–e tur-
approach, a fixed percentage of data points is randomly sampled,
bulence closure (Two-dimensional implementation of Eq. (1)
ensuring spatial representativeness in both the streamwise and span-
wise directions. This method also substantiates the findings of the
previous approaches, yielding similar mean RMSE values for a simi-
lar sample size. Based on this evidence, we adopt �4000 sampling
points for subsequent experiments as a practical compromise
between computational cost and predictive fidelity. The horizontal
plane of the computational domain spans 26D�17D, correspond-
ing to an area of 400456.42m2 for D¼30.1 m. While the CFD solver
employs 193776 grid points to resolve this plane, the PINN model
achieves comparable accuracy using only 2% of that number. That is
one sample point in approximately 100m2.
4. Effect of wall functions
To motivate the inclusion of wall functions in the PINN loss FIG. 17. Schematic of the domain for turbulent channel flow together with the
formulation, we conduct an ablation study based on a two- boundary conditions.
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-19
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 18. Comparison of mean velocity (U�), turbulent kinetic energy (k), and rate of dissipation of TKE (e) profiles at Res ¼180 for three PINN configurations against DNS
data:96 PINN with wall function (orange), PINN without wall function (green), and PINN without wall function with refinement (red).
without source terms). Periodic boundary conditions are applied at These findings demonstrate that wall functions are crucial, as
the inlet and outlet, and symmetry conditions are imposed at the they impose consistent boundary expressions for U�, k, and e,
top boundary. Two configurations are compared: (i) a baseline thereby restricting the admissible solution space and steering the
model, in which no wall function constraints are applied, and the PINN optimizer toward physically accurate solutions.
bottom boundary is placed at yþ¼0, and (ii) a wall-function
model, in which the bottom boundary is located at yþ¼31 (within
the log-law region, 30<yþ <500) and the following wall function APPENDIX D: IMPLEMENTATION DETAILS
expressions are enforced as boundary conditions:
1. Domain sampling
u¼
us
lnyþþB; k¼p
u
ffi
2
sffiffiffiffiffi; e¼
u3
s: (C1)
j Cl jy Figure 19 shows a three-dimensional schematic of the compu-
tational domain illustrating the sampling points used for the
All other hyperparameters, network architecture, and training set-
tings are held identical between the two configurations.
b. Results
Figure 18 presents a comparison of the predicted profiles of U�,
k, and e with the DNS reference data of Moser, Kim, and Mansour96
for the three PINN configurations at Res ¼180. The PINN employ-
ing wall functions (orange) reproduces the DNS profiles with good
accuracy across all three variables. The mean velocity profile exhibits
the expected logarithmic behavior and attains the correct centerline
value, while the k and e distributions remain in close agreement with
the DNS data over the entire channel height.
In contrast, neither of the PINN setups without wall functions
is able to reproduce the correct solution. The baseline model
(green), which uses the same number of collocation points as the
wall-function model, substantially underestimates the centerline
velocity and produces erroneous near-wall behavior in k and e.
This suggests that the optimizer has converged to an incorrect local
minimum in the loss landscape. Even increasing the number of col-
location points by an order of 10 relative to the baseline (red) fails
to resolve the issue: this higher-resolution model without wall func-
FIG. 19. Three-dimensional schematic of the domain sampling points showing the
tions still deviates markedly from the DNS data. This outcome
points used for different loss calculations. (i) Orange: boundary points (inlet, lateral
indicates that the optimization challenge cannot be attributed
rear, and top boundaries are shown), (ii) red: data points in a horizontal plane
solely to spatial resolution, but instead arises fundamentally from through the hub of the turbines, (iii) blue: domain collocation points, and (iv) green:
the lack of physically consistent near-wall boundary conditions. actuator disk region.
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-20
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 20. Two different sampling strategies for the data points in a horizontal plane through the hub of the turbines (a) grid-based and (b) random sampling. The bottom row
shows the sampling near the actuator disk region. The dense CFD mesh points are shown in blue.
different loss calculations during the training of the PINN model. APPENDIX E: EVALUATION ACROSS RANDOM
The domain consists of a rectangular volume enclosing the wind INITIALIZATIONS
turbine grid, with distributed sampling points for boundary, data,
The PINN model experiment was repeated with multiple
and PDE-residual losses. The orange points represent the domain
random seeds (N¼5) to account for stochastic variations in ini-
boundaries (Inlet, lateral rear, and top planes are shown in the fig-
tialization, data shuffling, and optimization. The domain with a
ure). These points are used to impose boundary conditions that
rectangular grid of turbines for U ¼9m=s at a turbulence
govern inflow velocity profiles, wall conditions, lateral confine- ref
intensity of 10% is simulated over multiple runs with different
ment, and outflow behavior. The red points define a horizontal
random seeds. The performance metrics reported in Tables IX
sampling plane intersecting the hub height of all turbines. The
and X represent the mean 6 standard deviation computed
streamwise velocity corresponding to the red points is used in the
in these independent runs for the RMSE between the simulation
hybrid training of the PINN model. The blue and green points cor-
from the PINN model and the numerical solver. The results
respond to the domain collocation points, where the governing
indicate consistent convergence behavior and limited depen-
equations are solved to evaluate the PDE-residual losses. A notice-
dence on initialization. This consistency supports the reproduc-
able refinement in point density is applied near the turbine regions
ibility and reliability of the proposed approach across
to better capture the strong velocity gradients and wake recovery. independent trials.
The green regions indicate the actuator disk zones, which model
the turbines as momentum sinks using the source terms in the gov-
erning equations. APPENDIX F: ERROR MAP
Figure 21 shows the comparison of velocity and turbulence
2. Data sampling intensity between the PINN model and the CFD solver in a vertical
Figure 20 shows two strategies used for data points sampling plane, along with the absolute error map.
in the horizontal plane passing through the hub height of the tur-
bines: (i) grid-based and (ii) random sampling. In both cases, the
APPENDIX G: DIAMOND GRID: SIMULATION
sampling points (shown in red) are overlaid on the computational
mesh (shown in blue), highlighting the underlying CFD resolution. Similar results shown for the rectangular grid of turbines in
In the grid-based sampling approach [Fig. 20(a)], data points are Sec. IIID are shown here for another pattern, the diamond grid
uniformly distributed over the plane with a constant spacing, and (Fig. 22). Figure 23 shows the contour plot of the RANS-PINN tur-
the random sampling approach [Fig. 20(b)] introduces stochastic bulent flow simulations (velocity, turbulence intensity, and pres-
variation in the spatial distribution of points. sure) in horizontal and two vertical planes (y=D¼63:5 and 0),
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-21
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids                                                                 A   R  T   I C  L  E             p  u bs.aip.org/aip/pof
TABLE IX. RMSE between the simulation from the PINN model and the numerical solver over multiple runs with different random seeds. Normalized velocity and TKE are
compared at the inlet, 3D, 6D, 9D, 12D, and 15D downstream of the turbine in a horizontal plane at the hub height of the wind turbines.
|     | Run 1 |     | Run 2 | Run 3 | Run 4 | Run 5 | Mean |
| --- | ----- | --- | ----- | ----- | ----- | ----- | ---- |
Inlet Normalized velocity 0.00144 0.00103 0.00077 0.00167 0.00105 0.0011960.00032
0.0047360.00146
| Normalized TKE | 0.00506 |     | 0.00387 | 0.00336 | 0.00744 | 0.00393 |     |
| -------------- | ------- | --- | ------- | ------- | ------- | ------- | --- |
3D Normalized velocity 0.00247 0.00181 0.00288 0.00195 0.00176 0.0021760.00043
Normalized TKE 0.31359 0.32014 0.31441 0.45291 0.54526 0.3892660.09433
6D Normalized velocity 0.00199 0.00202 0.00228 0.00229 0.00177 0.0020760.00020
Normalized TKE 0.38019 0.38483 0.35212 0.35449 0.54259 0.4028460.07110
9D Normalized velocity 0.00283 0.00245 0.00262 0.00151 0.00258 0.0024060.00046
Normalized TKE 0.57698 0.41227 0.38258 0.35736 0.67790 0.4814260.12464
0.0020860.00044
12D Normalized velocity 0.00229 0.00225 0.00237 0.00121 0.00229
Normalized TKE 0.64946 0.47087 0.41470 0.37687 0.59815 0.5020160.10511
15D Normalized velocity 0.00142 0.00222 0.00228 0.00091 0.00229 0.0018260.00056
Normalized TKE 0.66613 0.32290 0.27775 0.34403 0.51320 0.4248060.14463
TABLE X. RMSE between the simulation from the PINN model and the numerical solver over multiple runs with different random seeds. Normalized velocity and TKE are
compared at the inlet, 3D, 6D, 9D, 12D, and 15D downstream of the turbine in two vertical planes through the center of the wind turbines at 63:5D.
|     | y/D | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Mean |
| --- | --- | ----- | ----- | ----- | ----- | ----- | ---- |
Inlet Normalized velocity −3.5 0.03748 0.02928 0.02938 0.03601 0.02919 0.0322760.00369
0.0346460.01037
|     | 3.5 | 0.03025 | 0.02924 | 0.02924 | 0.05535 | 0.02910 |     |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --- |
 12 September 2026 13:03:32
Normalized TKE −3.5 0.01812 0.03211 0.02940 0.01842 0.02854 0.0253260.00587
|     | 3.5 | 0.01966 | 0.03598 | 0.03343 | 0.02480 | 0.03106 | 0.0289960.00596 |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --------------- |
3D Normalized velocity −3.5 0.05269 0.03121 0.03030 0.07082 0.03511 0.0440360.01565
|     | 3.5 | 0.07218 | 0.03439 | 0.03416 | 0.06063 | 0.03878 | 0.0480360.01553 |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --------------- |
Normalized TKE −3.5 0.31227 0.42069 0.38178 0.30800 0.37321 0.3591960.04315
|     | 3.5 | 0.44558 | 0.38878 | 0.36582 | 0.39901 | 0.43557 | 0.4069560.02965 |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --------------- |
0.0451360.01511
6D Normalized velocity −3.5 0.06548 0.03169 0.03068 0.06135 0.03644
|     | 3.5 | 0.06893 | 0.03592 | 0.03533 | 0.06300 | 0.03887 | 0.0484160.01451 |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --------------- |
Normalized TKE −3.5 0.34362 0.34623 0.31367 0.31489 0.32840 0.3293660.01374
|     | 3.5 | 0.43221 | 0.32248 | 0.30461 | 0.30746 | 0.38172 | 0.349760.04978 |
| --- | --- | ------- | ------- | ------- | ------- | ------- | -------------- |
9D Normalized velocity −3.5 0.07455 0.03274 0.03272 0.06152 0.03547 0.047460.01737
|     | 3.5 | 0.05132 | 0.03924 | 0.03949 | 0.05614 | 0.03814 | 0.0448760.00741 |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --------------- |
Normalized TKE −3.5 0.61056 0.48489 0.47368 0.47371 0.45692 0.4999560.05602
0.510460.04922
|     | 3.5 | 0.60185 | 0.50914 | 0.49894 | 0.45494 | 0.48715 |     |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --- |
12D Normalized velocity −3.5 0.07870 0.03669 0.03627 0.06588 0.03872 0.0512560.01767
|                | 3.5  | 0.05885 | 0.04098 | 0.04101 | 0.06620 | 0.04075 | 0.0495660.01084 |
| -------------- | ---- | ------- | ------- | ------- | ------- | ------- | --------------- |
|                | −3.5 |         |         |         |         |         | 0.5034460.08714 |
| Normalized TKE |      | 0.63141 | 0.46499 | 0.45351 | 0.57540 | 0.39190 |                 |
|                | 3.5  | 0.59035 | 0.45571 | 0.44819 | 0.55204 | 0.39008 | 0.4872760.0732  |
15D Normalized velocity −3.5 0.07531 0.04199 0.04158 0.07532 0.04303 0.0554560.01623
|     | 3.5 | 0.06815 | 0.04567 | 0.04572 | 0.07505 | 0.04512 | 0.0559460.01297 |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --------------- |
Normalized TKE −3.5 0.57624 0.46328 0.44909 0.55540 0.35611 0.4800260.07941
|     | 3.5 | 0.55975 | 0.44575 | 0.43706 | 0.52064 | 0.33902 | 0.4604460.07615 |
| --- | --- | ------- | ------- | ------- | ------- | ------- | --------------- |
passing through the hub of the wind turbines for the diamond grid.  APPENDIX H: RECTANGULAR GRID: SIMULATIONS
Figures 24 and 25 show the velocity and turbulent kinetic energy
1. Reference velocity: 8m/s
profiles in the horizontal and vertical planes, respectively, at differ-
ent downstream locations, along with the simulation from the CFD  Figure 26 shows the contour plot of the RANS-PINN turbu-
k–xSST solver for comparison. The simulations are shown for  lent flow simulations (velocity, turbulence intensity, and pressure)
U ¼10m=s. in horizontal and vertical planes passing through the hub of the
ref
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331                                                                                                                                                                 38, 055108-22
Published under an exclusive license by AIP Publishing

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 21. Contours showing comparison of velocity and turbulence intensity between PINN model and CFD solver in a vertical plane through the center of wind turbines in a
rectangular grid for U ¼9m=s. (a) PINN, (b) CFD, and (c) error map: (i) top: velocity magnitude and (ii) bottom: turbulence intensity.
ref
FIG. 22. Schematic of the diamond grid domain of wind turbines: (a) lateral view, (b) front view, and (c) top view. D is the diameter of the turbine, and H is the hub height.
The boundary conditions used on the domain surfaces are also shown.
2. Reference velocity: 10m/s
wind turbines for the rectangular grid. Figure 27 shows the velocity
and turbulent kinetic energy profiles in the two planes at different Figure 28 shows the contour plot of the RANS-PINN turbu-
downstream locations, along with the simulation from the CFD k– lent flow simulations (velocity, turbulence intensity, and pressure)
xSST solver for comparison. in horizontal and vertical planes passing through the hub of the
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-23
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 23. Contours of (a) velocity, (b) turbulence intensity, and (c) pressure in three planes through the center of wind turbines: (i) top: horizontal plane, (ii) middle: vertical
plane at y/D¼63:5, and (iii) bottom: vertical plane at y/D¼0.
FIG. 24. Comparison of (a) velocity and (b) turbulent kinetic energy predicted by the PINN model with the numerical solver in a horizontal plane at the hub height of the
wind turbines.
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-24
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 25. Comparison of (a) velocity and (b) turbulent kinetic energy predicted by the PINN model with the numerical solver in a vertical plane through the center of wind tur-
bines at y/D¼63:5 and 0.
FIG. 26. Contours of (a) velocity, (b) turbulence intensity, and (c) pressure in two planes through the center of wind turbines in a rectangular grid for U ¼8m=s: (i) top:
ref Horizontal plane and (ii) bottom: Vertical plane at y/D¼63:5.
FIG. 27. Comparison of (a) velocity and (b) turbulent kinetic energy predicted by PINN model with the numerical solver in two planes at the hub height of the wind turbines
in a rectangular grid for U ¼8m=s: (i) left: horizontal plane and (ii) right: vertical plane at y/D¼63:5.
ref
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-25
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 28. Contours of (a) velocity, (b) turbulence intensity, and (c) pressure in two planes through the center of wind turbines in a rectangular grid for U ¼10m=s: (i) top:
ref
horizontal plane and (ii) bottom: vertical plane at y/D¼63:5.
FIG. 29. Comparison of (a) velocity and (b) turbulent kinetic energy predicted by PINN model with the numerical solver in two planes at the hub height of the wind turbines
in a rectangular grid for U ¼10m=s: (i) left: horizontal plane and (ii) right: vertical plane at y/D¼63:5.
ref
3. Reference velocity: 11m/s
wind turbines for the rectangular grid. Figure 29 shows the velocity
and turbulent kinetic energy profiles in the two planes at different Figure 30 shows the contour plot of the RANS-PINN turbu-
downstream locations, along with the simulation from the CFD k– lent flow simulations (velocity, turbulence intensity, and pressure)
xSST solver for comparison. in horizontal and vertical planes, passing through the hub of the
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-26
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 30. Contours of (a) velocity, (b) turbulence intensity, and (c) pressure in two planes through the center of wind turbines in a rectangular grid for U ¼11m=s: (i) top:
ref
Horizontal plane and (ii) bottom: vertical plane at y/D¼63:5.
wind turbines for the rectangular grid. Figure 31 shows the velocity APPENDIX I: TRANSFER LEARNING: ADDITIONAL
and turbulent kinetic energy profiles in the two planes at different PLOTS
downstream locations, along with the simulation from the CFD k– Two simulation cases are conducted to demonstrate the effec-
xSST solver for comparison. tiveness of transfer learning: (i) how a higher-velocity test case can
FIG. 31. Comparison of (a) velocity and (b) turbulent kinetic energy predicted by PINN model with the numerical solver in two planes at the hub height of the wind turbines
in a rectangular grid for U ¼11m=s: (i) left: horizontal plane and (ii) right: vertical plane at y/D¼63:5.
ref
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-27
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 32. Velocity in a horizontal plane at the hub height of the wind turbines at different downstream locations simulated by the transfer learning strategy. (a) Higher velocity
(U ¼11m=s) simulation from pre-trained lower velocity (U ¼7;8;9;and10m=s) model and (b) lower velocity (U ¼7m=s) simulation from pre-trained higher veloc-
ref ref ref
ity (U ¼8;9;10;and11m=s) model. The dashed line is the target in each case. Markers denote the simulation after transfer learning, and the marker value is the U of
ref ref
the pre-trained model.
FIG. 33. Velocity in a horizontal plane at the hub height of the wind turbines at different downstream locations simulated by the transfer learning strategy. U¼9m/s at turbu-
lence intensities of (a) 6% and (b) 8% simulations from pre-trained model with U¼7and11m/s at turbulence intensity of 10%. The dashed line is the target in each case.
Markers denote the simulation after transfer learning, and the marker values indicate velocity and turbulence intensity of the pre-trained model.
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-28
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
FIG. 34. Contours of (a) velocity, (b) turbulence intensity, and (c) pressure in the horizontal plane through the center of wind turbines in a rectangular grid for U ¼9m=s
ref
simulated using a pure data-driven approach.
be quickly simulated from a pre-trained lower-velocity PINN Nacional em Mec^anica de Fluidos, Termodin^amica e Energia (MEFTE-
model and vice versa, while maintaining a constant turbulence BRAGANC¸A 09) p3 Paper (in CD) [Associac¸~ao Portuguesa de Mec^anica
intensity across the simulations, and (ii) how a test case with differ- Te�orica, Aplicada e Computacional (APMTAC), 2009], pp. 1–31.
06M. Breuer, N. Jovi�ci�c, and K. Mazaev, “Comparison of DES, RANS and LES
ent velocity and turbulence intensity can be simulated from a pre-
for the separated flow around a flat plate at high incidence,” Int. J. Numer.
trained model with different conditions. Figures 32 and 33
Methods Fluids 41, 357–388 (2003).
compare the velocity in a horizontal plane at the hub height of the 07X. Zhu, E. Phillips, V. Spandan, J. Donners, G. Ruetsch, J. Romero, R. Ostilla-
wind turbines at different downstream locations for case i and case Mo�nico, Y. Yang, D. Lohse, R. Verzicco et al., “AFiD-GPU: A versatile navier–
ii, respectively. stokes solver for wall-bounded turbulent flows on GPU clusters,” Comput.
Phys. Commun. 229, 199–210 (2018).
08P. Costa, E. Phillips, L. Brandt, and M. Fatica, “GPU acceleration of cans for
APPENDIX J: WHY PHYSICS-INFORMED? massively-parallel direct numerical simulations of canonical fluid flows,”
Comput. Math. Appl. 81, 502–511 (2021).
Figure 34 illustrates why incorporating physical constraints is 09M. Bernardini, D. Modesti, F. Salvadore, and S. Pirozzoli, “Streams: A high-
essential when only sparse or partial data are available. In this case, fidelity accelerated solver for direct numerical simulation of compressible tur-
bulent flows,” Comput. Phys. Commun. 263, 107906 (2021).
velocity measurements were used as the sole supervisory data
10F. De Vanna, F. Avanzi, M. Cogo, S. Sandrin, M. Bettencourt, F. Picano, and
source. Still, the velocity contours show deviation as indicated by
E. Benini, “Uranos: A GPU accelerated navier-stokes solver for compressible
the elevated values between the turbines [Fig. 34(a)]. Because no
wall-bounded flows,” Comput. Phys. Commun. 287, 108717 (2023).
data were provided for turbulence or pressure fields, purely data- 11M. Crialesi-Esposito, N. Scapin, A. D. Demou, M. E. Rosti, P. Costa, F. Spiga,
driven learning fails to recover the correct physical behavior in and L. Brandt, “Flutas: A GPU-accelerated finite difference code for multiphase
these variables. This is evident in the poor predictions of turbu- flows,” Comput. Phys. Commun. 284, 108602 (2023).
lence intensity [Fig. 34(b)] and pressure [Fig. 34(c)], both of which 12A. Radhakrishnan, H. Le Berre, B. Wilfong, J.-S. Spratt, M. Rodriguez, Jr., T.
Colonius, and S. H. Bryngelson, “Method for scalable and performant GPU-
show clear inconsistencies. These results demonstrate that relying
accelerated simulation of multiphase compressible flow,” Comput. Phys.
solely on data—especially when limited to a single variable—cannot
Commun. 302, 109238 (2024).
guarantee physically consistent predictions across all flow quanti- 13A. Di Bella, M. Raissi, D. Santoro, and P. Roccaro, “Physics-informed neural
ties. Physics-informed training overcomes this limitation by networks in water and wastewater systems: A critical review,” Water Res. 293,
enforcing the governing equations, enabling the model to infer 125449 (2026).
unmeasured variables in a physically valid manner. 14J. D. Toscano, V. Oommen, A. J. Varghese, Z. Zou, N. Ahmadi Daryakenari, C.
Wu, and G. E. Karniadakis, “From pinns to pikans: Recent advances in physics-
informed machine learning,” Mach. Learn. Comput. Sci. Eng. 1, 1–43 (2025).
REFERENCES 15L. Lu, P. Jin, G. Pang, Z. Zhang, and G. E. Karniadakis, “Learning nonlinear
01P. Moin and K. Mahesh, “Direct numerical simulation: A tool in turbulence operators via deeponet based on the universal approximation theorem of oper-
research,” Annu. Rev. Fluid Mech. 30, 539–578 (1998). ators,” Nat. Mach. Intell. 3, 218–229 (2021).
02P. J. Mason, “Large-eddy simulation: A critical review of the technique,” Q. J. 16Z. Li, N. Kovachki, K. Azizzadenesheli, B. Liu, K. Bhattacharya, A. Stuart, and
R. Meteorol. Soc. 120, 1–26 (1994). A. Anandkumar, “Fourier neural operator for parametric partial differential
03C. G. Speziale, “Analytical methods for the development of reynolds-stress equations,” arXiv:2010.08895 (2020).
closures in turbulence,” Annu. Rev. Fluid Mech. 23, 107–157 (1991). 17R. Alaifari, F. Bartolucci, E. de Bezenac, R. Molinaro, S. Mishra, and B. Raonic,
04J. P. Slotnick, A. Khodadoust, J. Alonso, D. Darmofal, W. Gropp, E. Lurie, and “Representation equivalent neural operators: A framework for alias-free operator
D. J. Mavriplis, “CFD vision 2030 study: A path to revolutionary computa- learning,” Adv. Neural Inf. Process. Syst. 36, 69661–69672 (2024).
tional aerosciences,” Report No. NF1676L-18332 (NASA, Boeing Research & 18N. Kovachki, Z. Li, B. Liu, K. Azizzadenesheli, K. Bhattacharya, A. Stuart, and
Technology, Huntington Beach, CA, 2014). A. Anandkumar, “Neural operator: Learning maps between function spaces
05C. D. P�erez-Segarra, O. Lehmkuhl, J. Jaramillo, G. Colomer, and A. Oliva, with applications to PDEs,” J. Mach. Learn. Res. 24, 1–97 (2023).
“Turbulence modelling and numerical issues: From rans to DNS and LES,” in 19M. Optis and J. Perr-Sauer, “The importance of atmospheric turbulence and
Actas da III Confer^encia Nacional em Mec^anica de Fluidos, Termodin^amica e stability in machine-learning models of wind farm power production,”
Energia (MEFTE-BRAGANC¸A 09) p3 Paper (in CD) (Actas da III Confer^encia Renewable Sustainable Energy Rev. 112, 27–41 (2019).
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-29
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
20Z. Ti, X. W. Deng, and H. Yang, “Wake modeling of wind turbines using 42A. Gafoor CTP, S. K. Boya, R. Jinka, A. Gupta, A. Tyagi, S. Sarkar, and D. N.
machine learning,” Appl. Energy 257, 114025 (2020). Subramani, “A physics-informed neural network for turbulent wake simula-
21Z. Ti, X. W. Deng, and M. Zhang, “Artificial neural networks based wake tions behind wind turbines,” Phys. Fluids 37, 015110 (2025).
model for power prediction of wind farm,” Renewable Energy 172, 618–631 43P. Cobelli, K. Shukla, S. Nesmachnow, and M. Draper, “Physics informed neu-
(2021). ral networks for wind field modeling in wind farms,” J. Phys.: Conf. Ser. 2505,
22J. Zhang and X. Zhao, “A novel dynamic wind farm wake model based on 012051 (2023).
deep learning,” Appl. Energy 277, 115552 (2020). 44J. Zhang and X. Zhao, “Digital twin of wind farms via physics-informed deep
23Z. Zhang, C. Santoni, T. Herges, F. Sotiropoulos, and A. Khosronejad, “Time- learning,” Energy Convers. Manage. 293, 117507 (2023).
averaged wind turbine wake flow field prediction using autoencoder convolu- 45L. Wang, M. Chen, Z. Luo, B. Zhang, J. Xu, Z. Wang, and A. C. Tan,
tional neural networks,” Energies 15, 41 (2021). “Dynamic wake field reconstruction of wind turbine through physics-
24P. M. Doran, “Chapter 7 - fluid flow,” in Bioprocess Engineering Principles, 2nd informed neural network and sparse LiDAR data,” Energy 291, 130401 (2024).
ed., edited by P. M. Doran (Academic Press, London, 2013), pp. 201–254. 46J. Song, L. Wang, Z. Xin, and H. Wang, “Wake field prediction of a wind farm
25M. Raissi, P. Perdikaris, and G. E. Karniadakis, “Physics-informed neural net- based on a physics-informed neural network with different spatiotemporal
works: A deep learning framework for solving forward and inverse problems prediction performance improvement strategies,” Theor. Appl. Mech. Lett. 15,
involving nonlinear partial differential equations,” J. Comput. Phys. 378, 686– 100577 (2025).
707 (2019). 47K. Liu, K. Luo, Y. Cheng, A. Liu, H. Li, J. Fan, and S. Balachandar,
26A. G. Baydin, B. A. Pearlmutter, A. A. Radul, and J. M. Siskind, “Automatic “Parameterized physics-informed neural networks (p-pinns) solution of uni-
differentiation in machine learning: A survey,” J. Mach. Learn. Res. 18, 1–43 form flow over an arbitrarily spinning spherical particle,” Int. J. Multiphase
(2018). Flow 180, 104937 (2024).
27A. Krishnapriyan, A. Gholami, S. Zhe, R. Kirby, and M. W. Mahoney, 48W. Cao, S. Tang, Q. Ma, W. Ouyang, and W. Zhang, “Solving all laminar flows
“Characterizing possible failure modes in physics-informed neural networks,” around airfoils all-at-once using a parametric neural network solver,”
Adv. Neural Inf. Process. Syst. 34, 26548–26560 (2021). arXiv:2501.01165 (2025).
28S. Wang, Y. Teng, and P. Perdikaris, “Understanding and mitigating gradient 49Z. Cao, K. Liu, K. Luo, Y. Cheng, and J. Fan, “Efficient optimization design of
flow pathologies in physics-informed neural networks,” SIAM J. Sci. Comput. flue deflectors through parametric surrogate modeling with physics-informed
43, A3055–A3081 (2021). neural networks,” Phys. Fluids 35, 125149 (2023).
29Y. Sun, U. Sengupta, and M. Juniper, “Physics-informed deep learning for 50V. Kag, K. Seshasayanan, and V. Gopinath, “Physics-informed data based neu-
simultaneous surrogate modeling and pde-constrained optimization of an air- ral networks for two-dimensional turbulence,” Phys. Fluids 34, 055130 (2022).
foil geometry,” Comput. Methods Appl. Mech. Eng. 411, 116042 (2023). 51S. Wang, S. Sankaran, X. Fan, P. Stinis, and P. Perdikaris, “Simulating three-
30X. Jin, S. Cai, H. Li, and G. E. Karniadakis, “NSFnets (Navier–Stokes flow dimensional turbulence with physics-informed neural networks,”
nets): Physics-informed neural networks for the incompressible navier-stokes arXiv:2507.08972 (2025).
equations,” J. Comput. Phys. 426, 109951 (2021). 52S. Cai, Z. Mao, Z. Wang, M. Yin, and G. E. Karniadakis, “Physics-informed
31S. Luo, M. Vellakal, S. Koric, V. Kindratenko, and J. Cui, “Parameter identifica- neural networks (pinns) for fluid mechanics: A review,” Acta Mech. Sin. 37,
tion of rans turbulence model using physics-embedded neural network,” in 1727–1738 (2021).
International Conference on High Performance Computing (Springer, 2020), pp. 53S. Cuomo, V. S. Di Cola, F. Giampaolo, G. Rozza, M. Raissi, and F. Piccialli,
137–149. “Scientific machine learning through physics–informed neural networks:
32O. Hennigh, S. Narasimhan, M. A. Nabian, A. Subramaniam, K. Tangsali, Z. Where we are and what’s next,” J. Sci. Comput. 92, 88 (2022).
Fang, M. Rietmann, W. Byeon, and S. Choudhry, “Nvidia simnetTM: An ai- 54C. Zhao, F. Zhang, W. Lou, X. Wang, and J. Yang, “A comprehensive review
accelerated multi-physics simulation framework,” in International Conference of advances in physics-informed neural networks and their applications in
on Computational Science (Springer, 2021), pp. 447–461. complex fluid dynamics,” Phys. Fluids 36, 101301 (2024).
33S. Ghosh, A. Chakraborty, G. O. Brikis, and B. Dey, “RANS-PINN based simu- 55B. E. Launder and B. I. Sharma, “Application of the energy-dissipation model
lation surrogates for predicting turbulent flows,” arXiv:2306.06034 (2023). of turbulence to the calculation of flow near a spinning disc,” Lett. Heat Mass
34H. Eivazi, M. Tahani, P. Schlatter, and R. Vinuesa, “Physics-informed neural Transfer 1, 131–137 (1974).
networks for solving Reynolds-averaged Navier–Stokes equations,” Phys. 56A. Crespo, F. Manuel, D. Moreno, E. Fraga, and J. Hernandez, “Numerical analysis
Fluids 34, 075117 (2022). of wind turbine wakes,” in Workshop on Wind Energy Applications, Delphi, Greece
35S. K. Biswas and N. Anand, “Three-dimensional laminar flow using physics (Workshop on Wind Energy Applications, Delphi, Greece, 1985), pp. 15–25.
informed deep neural networks,” Phys. Fluids 35, 121703 (2023). 57P. Rathore, W. Lei, Z. Frangella, L. Lu, and M. Udell, “Challenges in training
36S. Hu, M. Liu, S. Zhang, S. Dong, and R. Zheng, “Physics-informed neural net- pinns: A loss landscape perspective,” arXiv:2402.01868 (2024).
work combined with characteristic-based split for solving Navier–Stokes equa- 58W. T. Leung, G. Lin, and Z. Zhang, “NH-PINN: Neural homogenization-
tions,” Eng. Appl. Artif. Intell. 128, 107453 (2024). based physics-informed neural network for multiscale problems,” J. Comput.
37E.-Z. Rui, Z.-W. Chen, Y.-Q. Ni, L. Yuan, and G.-Z. Zeng, “Reconstruction of Phys. 470, 111539 (2022).
3D flow field around a building model in wind tunnel: A novel physics- 59R. Bischof and M. A. Kraus, “Multi-objective loss balancing for physics-informed
informed neural network framework adopting dynamic prioritization self- deep learning,” Comput. Methods Appl. Mech. Eng. 439, 117914 (2025).
adaptive loss balance strategy,” Eng. Appl. Comput. Fluid Mech. 17, 2238849 60B. E. Launder and D. B. Spalding, “The numerical computation of turbulent
(2023). flows,” Comput. Methods Appl. Mech. Eng. 3, 269–289 (1974).
38P. Clark Di Leoni, K. Agarwal, T. A. Zaki, C. Meneveau, and J. Katz, 61G. Kalitzin, G. Medic, G. Iaccarino, and P. Durbin, “Near-wall behavior of rans
“Reconstructing turbulent velocity and pressure fields from under-resolved turbulence models and implications for wall functions,” J. Comput. Phys. 204,
noisy particle tracks using physics-informed neural networks,” Exp. Fluids 64, 265–291 (2005).
95 (2023). 62B. Blocken, T. Stathopoulos, and J. Carmeliet, “CFD simulation of the atmo-
39G. S. Hora, P. Gentine, M. Momen, and M. G. Giometto, “Physics-informed spheric boundary layer: Wall function problems,” Atmos. Environ. 41, 238–
data-driven reconstruction of turbulent wall-bounded flows from planar mea- 252 (2007).
surements,” Phys. Fluids 36, 115191 (2024). 63J. N. Sørensen, “Aerodynamic aspects of wind energy conversion,” Annu. Rev.
40J. Zhang and X. Zhao, “Spatiotemporal wind field prediction based on Fluid Mech. 43, 427–448 (2011).
physics-informed deep learning and lidar measurements,” Appl. Energy 288, 64Y.-S. Chen and S.-W. Kim, “Computation of turbulent flow using an extended
116641 (2021). turbulence closure model,” Report No. NAS 1.26: 179204 (NASA, 1987).
41J. Zhang and X. Zhao, “Three-dimensional spatiotemporal wind field recon- 65A. El Kasmi and C. Masson, “An extended k–e model for turbulent flow
struction based on physics-informed deep learning,” Appl. Energy 300, 117390 through horizontal-axis wind turbines,” J. Wind Eng. Ind. Aerodyn. 96, 103–
(2021). 122 (2008).
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-30
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32

Physics of Fluids A R T I C L E p u bs.aip.org/aip/pof
66M. Abadi, A. Agarwal, P. Barham, E. Brevdo, Z. Chen, C. Citro, G. S. Corrado, 81M. Puccioni, C. Moss, C. Jacquet, and G. Iungo, “Blockage and speedup in the
A. Davis, J. Dean, M. Devin, S. Ghemawat, I. Goodfellow, A. Harp, G. Irving, proximity of an onshore wind farm: A scanning wind lidar experiment,”
M. Isard, Y. Jia, R. Jozefowicz, L. Kaiser, M. Kudlur, J. Levenberg, D. Man�e, R. J. Renewable Sustainable Energy 15, 053307 (2023).
Monga, S. Moore, D. Murray, C. Olah, M. Schuster, J. Shlens, B. Steiner, I. 82H. Lu, X. Gao, Z. Xu, H. Xiao, Y. Gao, H. Zhang, H. Ma, Y. Zhu, X. Zhu, and
Sutskever, K. Talwar, P. Tucker, V. Vanhoucke, V. Vasudevan, F. Vi�egas, O. Y. Wang, “Wind direction prediction combined with wind speed in a wind
Vinyals, P. Warden, M. Wattenberg, M. Wicke, Y. Yu, and X. Zheng, see ten- farm,” Energy 333, 137334 (2025).
sorflow.org for “TensorFlow: Large-scale machine learning on heterogeneous 83T. Mikkelsen, N. Angelou, K. Hansen, M. Sjo€holm, M. Harris, C. Slinger, P.
systems” (2015). Hadley, R. Scullion, G. Ellis, and G. Vives, “A spinner-integrated wind lidar
67A. Gafoor CTP, see https://github.com/quest-lab-iisc/PINN_WakeTurbulence for enhanced wind turbine control,” Wind Energy 16, 625–643 (2013).
Model “A PINN for turbulent wake simulations” (2024). 84N. Angelou and M. Sjo€holm, “Data reliability enhancement for wind-turbine-
68D. V. Dung, N. D. Song, P. S. Palar, and L. R. Zuhal, “On the choice of activa- mounted lidars,” Remote Sens. 14, 3225 (2022).
tion functions in physics-informed neural network for solving incompressible 85M. F. Van Dooren, D. Trabucchi, and M. Ku€hn, “A methodology for the
fluid flows,” AIAA Paper No. 2023-1803, 2023. reconstruction of 2d horizontal wind fields of wind turbine wakes based on
69D. P. Kingma, “Adam: A method for stochastic optimization,” dual-doppler lidar measurements,” Remote Sens. 8, 809 (2016).
arXiv:1412.6980 (2014). 86J. P. Goit, S. Shimada, and T. Kogaki, “Can lidars replace meteorological masts
70X. Glorot and Y. Bengio, “Understanding the difficulty of training in wind energy?,” Energies 12, 3680 (2019).
deep feedforward neural networks,” in Proceedings of the Thirteenth 87G. V. Iungo, “Experimental characterization of wind turbine wakes: Wind tun-
International Conference on Artificial Intelligence and Statistics (JMLR, nel tests and wind lidar measurements,” J. Wind Eng. Ind. Aerodyn. 149, 35–
2010), pp. 249–256. 39 (2016).
71A. Gafoor CTP (2026). “A PINN for multi-turbine turbulent wake simulation 88Siemens Digital Industries Software, see https://www.plm.automation.siemen-
using physics-informed neural networks,” GitHub and Zenodo. https://github.- s.com/global/en/products/simcenter/STAR-CCM.html for “Simcenter STAR-
com/quest-lab-iisc/PINNs_multi_turbine_wake_simulation CCMþ, version 2021.1” (Siemens 2021).
72R. E. Froude, “On the part played in propulsion by differences of fluid pres- 89F. R. Menter, “Two-equation eddy-viscosity turbulence models for engineering
sure,” Trans. Inst. Nav. Archit. 30, 390 (1889). applications,” AIAA J. 32, 1598–1605 (1994).
73J. N. Sørensen and A. Myken, “Unsteady actuator disc model for horizontal 90E. G. Antonini, D. A. Romero, and C. H. Amon, “Analysis and modifications
axis wind turbines,” J. Wind Eng. Ind. Aerodyn. 39, 139–149 (1992). of turbulence models for wind turbine wake simulations in atmospheric
74P. J. Richards and R. P. Hoxey, “Appropriate boundary conditions for compu- boundary layers,” J. Sol. Energy Eng. 140, 031007 (2018).
tational wind engineering models using the k-e turbulence model,” J. Wind 91A. Rezaeiha, H. Montazeri, and B. Blocken, “On the accuracy of turbulence
Eng. Ind. Aerodyn. 46–47, 145–153 (1993). models for CFD simulations of vertical axis wind turbines,” Energy 180, 838–
75A. Parente, C. Gorl�e, J. Van Beeck, and C. Benocci, “Improved k–e model and 857 (2019).
wall function formulation for the rans simulation of abl flows,” J. Wind Eng. 92N. Stergiannis, J. van Beeck, and M. C. Runacres, “Full HAWT rotor CFD sim-
Ind. Aerodyn. 99, 267–278 (2011). ulations using different rans turbulence models compared with actuator disk
76J. Hammersley and D. Handscomb, Monte Carlo Methods (Methuen & Co, and experimental measurements,” Wind Energy Sci. Discuss. 2017, 1–20.
Ltd., London, 1964), Vol. 40, p. 32. 93S. K. Boya and D. N. Subramani, “PINTO: Physics-informed transformer neu-
77C. Wu, M. Zhu, Q. Tan, Y. Kartha, and L. Lu, “A comprehensive study of non- ral operator for learning generalized solutions of partial differential equations
adaptive and residual-based adaptive sampling for physics-informed neural for any initial and boundary condition,” Comput. Phys. Commun. 315,
networks,” Comput. Methods Appl. Mech. Eng. 403, 115671 (2023). 109702 (2025).
78L. Vermeer, J. N. Sørensen, and A. Crespo, “Wind turbine wake aerodynam- 94S. Goswami, C. Anitescu, S. Chakraborty, and T. Rabczuk, “Transfer learning
ics,” Prog. Aerosp. Sci. 39, 467–510 (2003). enhanced physics informed neural network for phase-field modeling of frac-
79Y.-T. Wu and F. Port�e-Agel, “Atmospheric turbulence effects on wind-turbine ture,” Theor. Appl. Fract. Mech. 106, 102447 (2020).
wakes: An Les study,” Energies 5, 5340–5362 (2012). 95S. Desai, M. Mattheakis, H. Joy, P. Protopapas, and S. Roberts, “One-shot transfer
80P. K. Jha, E. P. Duque, J. L. Bashioum, and S. Schmitz, “Unraveling the learning of physics-informed neural networks,” arXiv:2110.11286 (2021).
mysteries of turbulence transport in a wind farm,” Energies 8, 6468–6496 96R. D. Moser, J. Kim, and N. N. Mansour, “Direct numerical simulation of tur-
(2015). bulent channel flow up to Re s¼590,” Phys. Fluids 11, 943–945 (1999).
Phys. Fluids 38, 055108 (2026); doi: 10.1063/5.0322331 38, 055108-31
Published under an exclusive license by AIP Publishing
12
September
2026
13:03:32
