<!-- markitdown-mirror: source="尾流PINN论文1_Gafoor2025_PhysFluids37-015110_单机尾流PINN_doi10.1063-5.0245113.pdf" sha256="56851ca5b8eb" generated="2026-09-21" | 只读镜像，正文由 microsoft/markitdown 自动转换，以同目录原文件为准；重新生成：python3 tools/markitdown_sync.py -->

RESEARCH ARTICLE | JANUARY 02 2025
A physics-informed neural network for turbulent wake
simulations behind wind turbines
Azhar Gafoor CTP ; Sumanth Kumar Boya ; Rishi Jinka ; Abhineet Gupta ; Ankit Tyagi ;
Suranjan Sarkar ; Deepak N. Subramani
Physics of Fluids 37, 015110 (2025)
https://doi.org/10.1063/5.0245113
 
View Export
Online Citation
Articles You May Be Interested In
Influence of atmospheric thermal stability on wake meandering of a large-scale wind turbine
Physics of Fluids (November 2025)
Multi-turbine turbulent wake simulation using physics-informed neural networks
Physics of Fluids (May 2026)
Flow in a large wind field with multiple actuators in the presence of constant vorticity
Physics of Fluids (October 2022)
12
September
2026
13:02:35

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
A physics-informed neural network for turbulent
wake simulations behind wind turbines
Citeas:Phys.Fluids37,015110(2025);doi:10.1063/5.0245113
. .
Submitted:23October2024 Accepted:3December2024
PublishedOnline:2January2025
AzharGafoorCTP,1 SumanthKumarBoya,1 RishiJinka,1 AbhineetGupta,2 AnkitTyagi,2
SuranjanSarkar,2 andDeepakN.Subramani1,a)
AFFILIATIONS
1DepartmentofComputationalandDataSciences,IndianInstituteofScience,Bangalore,Karnataka560012,India
2ShellIndiaMarketsPvt.Ltd.,Bangalore,Karnataka560103,India
a)Authortowhomcorrespondenceshouldbeaddressed:deepakns@iisc.ac.in
ABSTRACT
Fast simulations of wind turbine wakes are crucial during the design phase of optimal wind farm layouts. Wind turbine wakes affect the
performanceofdownstreamturbines.Physics-informedneuralnetworks(PINNs),adeeplearningapproachtosimulatedynamicalsystems
governed by partial differential equations, are gaining traction in computational fluid dynamics due to their fast inference capability. We
developedaPINNmodelusingthe2-equationk(cid:1)emodelandtheactuatordiskmethodtosimulatethewakesbehindthewindturbines.
Crucially,trainingofthedevelopedPINNmodeldoesnotrelyonhigh-fidelitysimulationdata,thusreducingtheend-to-endtrainingtime
by saving simulation data generation time. We tested the model against traditional solvers and field data to simulate the turbulent wake
behindtheHOLECWPS30/3WindTurbinefromSexbierumandathree-blade630-kWNibe-Bwindturbine.Detailedcomputationalstud-
ies are completed to establish convergence properties with increasing sampling collocation points and the number of graphical processing
units.Atransferlearningstrategyisintroducedtoacceleratetrainingfornewscenariosresultingina5(cid:3)speedup.Ourresultsestablishthe
efficacy of the PINN model in simulating turbulent flows. Compared to field data, our PINN model and traditional Reynolds-averaged
Navier–Stokes(RANS)numericalsolvers,suchastheshearstresstransportk(cid:1)xandReynoldsstressmodelhavesimilarerrors,suggesting
its utility as a replacement to these RANS solvers. The model architecture, trained weights, and code are available in https://github.com/
quest-lab-iisc/PINN_WakeTurbulenceModel.
PublishedunderanexclusivelicensebyAIPPublishing.https://doi.org/10.1063/5.0245113
I.INTRODUCTION turbulence closure mechanism. Large eddy simulation (LES)5 and
Thesimulationofturbulentflowsplaysavitalroleinvarioussci- Reynolds-averagedNavier–Stokes(RANS)6arethepopularturbulence
entific fields, such as renewable energy, astrophysics, geology, and closuremodelsused.Amongthetwo,RANSstrikesabalancebetween
weather forecasting. Anestimate of the turbulent wake behind wind accuracy and computational efficiency, making it a preferred choice
turbinesiscrucialforseveralapplications,suchasnewturbinedesign, for complex industrial problems for the foreseeable
future.7–9
estimationofpoweroutputunderdifferentwindconditions,andopti- Traditionally,simulationsareperformedbysolvingtheseequationson
mizationofthelayoutofwindfarms.Thetotalpoweroutputofawind adiscretizedspatiotemporaldomainusingnumericalschemes,suchas
farmdependsonthelossofwindspeedinthewakeofindividualtur- finite difference, finite volume, finite element, and spectral methods.
bines. Thus, simulating the flow accurately behind one turbine is All of these methods require heavy computation on many-core sys-
important. Furthermore, in low-resource economies such as India, temsanddonothavetheoptionforfastinferenceonanewconfigura-
Venezuela,etc.,single-turbinepowerplantsarecommon.1–3Thegoal
tion without solving the partial differential equations (PDEs) from
ofthepresentpaperistodevelopaneuralnetworkmodelasafastsur- scratchagain.
rogateforsimulatingthewakebehindonewindturbinethatissubject Artificial Intelligence (AI) systems that use neural networks
towind. trainedongraphicalprocessingunits(GPUs)havegainedpopularity
TheturbulentwakeflowisgovernedbynonlinearNavier–Stokes acrossvariousdomains,suchastextandimageprocessing,andmore
(NS)equations.Traditionally,theseequationsaresolvednumerically recentlyfornumericalsolutionofPDEs.ThemajoradvantageofanAI
either directly (called direct numerical simulation, DNS4) or using a solution is that once the system is trained, inference on new
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-1
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

| Physics | of Fluids |     |     |     |     |     |     |     | ARTICLE |     |     | pubs.aip.org/aip/pof |     |     |     |
| ------- | --------- | --- | --- | --- | --- | --- | --- | --- | ------- | --- | --- | -------------------- | --- | --- | --- |
methods.16–21
configurations is fast. However, unlike text and image applications, experimental or high-fidelity data from numerical
generatingdatatotrainneuralnetworksisexpensiveforfluidsimula- Various machine learning techniquesand models suchas the kernel
tions.Datagenerationrequiresrunningtraditionalnumericalmethods regression method,22,23 random forest-based approaches,24–26 and
onmanycoresystemsoverdaysandweeks.10Fortunately,amethodol- tensor-basisneuralnetwork(TBNN)27havebeenimplementedforthe
| ogy known | as physics-informed |     | neural | networks | (PINN) | solves the |     |     |     |     |     |     |     |     |     |
| --------- | ------------------- | --- | ------ | -------- | ------ | ---------- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
same.Studieshavebeencompletedontheconvergenceofsuchcou-
computations.28,29
problemofdatarequirementbyusinganewlossfunctionthatisthe pled ML-CFD Another approach in ML-augment
weighted sum of the residual PDE (representing the physics of the CFDistouseCFDononepartofthedomain,usethosedatatotrain
problem)andthemeansquareerrorofthedatafromtheboundary/ anMLmodel,anduseittopredictotherpartsofthedomain.30,31One
initialconditions.11Theinnovationwastouseautomaticdifferentia- major drawback is that using only DNS data (and not experimental
tion12throughtheneuralnetworktocalculatetheresidualPDE,elimi- data)tomodelclosuretermsinRANScanresultinpoorestimatesdue
natingtheneedforsimulationdatatoinformthephysicsoftheneural totheinconsistencybetweenDNSandRANSmodels.32–34Inaddition,
modelduringtraining.Anotherprevalentapproachtotraintheseneu- overfittingcancausetheresultantMLmodelstoviolatethegoverning
| ral models | (e.g., | DeepONet,13 | Fourier | Neural | Operator,14 | and |          | laws.35 |            |     |        |            |     |               |     |
| ---------- | ------ | ----------- | ------- | ------ | ----------- | --- | -------- | ------- | ---------- | --- | ------ | ---------- | --- | ------------- | --- |
|            |        |             |         |        |             |     | physical |         | Estimation |     | of PDE | parameters | and | the discovery | of  |
RepresentationequivalentNeuralOperators15)istoleveragedatafrom
|             |     |             |           |          |     |               | equations, |                  | posed | as inverse | problems,   | have | been tackled | using   | sym-     |
| ----------- | --- | ----------- | --------- | -------- | --- | ------------- | ---------- | ---------------- | ----- | ---------- | ----------- | ---- | ------------ | ------- | -------- |
| traditional | PDE | solvers for | training. | Although |     | both of these |            | regression,36,37 |       |            |             |      |              |         |          |
|             |     |             |           |          |     |               | bolic      |                  |       | sparse     | regression, | and  | other        | machine | learning |
methods.38–41PDE-Netusesconvolutionstoapproximatedifferential
approacheshaveshownsuccessinsimulatingcertainnonlinearPDEs,
their applicability to highly turbulent flows remains unproven. operationsandlearnPDEsfromdata.42,43
Specifically, the development of PINN models to simulate turbulent Inthesecondbucket,thefirsttrackisdevelopingneuralmodels
Navier–Stokes
flows governed by Reynolds-averaged (RANS) equa- forflowsimulationusingsimulationdatafromtraditionalCFDmeth-
tionsusingresidual-driventraininghasnotbeendonepreviously.The ods to develop reduced-order models of fluid flow dynamics.44–46 A
PINNmodelalsoavoidsthecomplexdiscretizationprocessinconven- data-drivensurrogatetohigh-fidelitynumericalflowsimulationswas
tionalnumericalsolvers.
|     |     |     |     |     |     |     | developed |     | employing | a   | deep convolutional |     | neural | network | trained |
| --- | --- | --- | --- | --- | --- | --- | --------- | --- | --------- | --- | ------------------ | --- | ------ | ------- | ------- |
The purpose of the present paper is to address the above- usingdigitalimages.47Neuraloperatormodels48trainedpurelyfrom
mentionedresearchgapbydevelopinganddemonstratingtheability
simulationdatahavebeendevelopedonthebasisoftheirunderlying
ofPINNmodelstomodeltheturbulentwakebehindwindturbines. principles. The most popular are Fourier neural operators (FNO)
Ourmotivationistoperformtrainingwithoutusinghigh-fidelitysim- based on the Fourier transform,14 graph neural operators based on  12 September 2026 13:02:35
ulationdatafromtraditionalsolvers.Wewanttoaddresskeymethod- graph kernel learning,49 and convolutional neural operator (CNO)
ologicalquestionssuchas(i)Whatistherelationshipbetweentraining basedonconvolutionalneuralnetworks(CNN)withU-Netarchitec-
| collocation  | sampling           | pointsand | solution  | convergence?(ii) |                | What are | ture.50 |     |        |       |               |     |               |     |          |
| ------------ | ------------------ | --------- | --------- | ---------------- | -------------- | -------- | ------- | --- | ------ | ----- | ------------- | --- | ------------- | --- | -------- |
|              |                    |           |           |                  |                |          |         | The | second | track | is developing |     | neural models | by  | training |
| the best set | of hyperparameters |           | including | the              | loss weighting | factor?  |         |     |        |       |               |     |               |     |          |
againstPDEresidualsthatarecalculatedusingautomaticdifferentia-
(iii)WhatistheimpactofusingmultipleGPUsfortraining?and(iv)
|     |     |     |     |     |     |     | tion | through | the | neural | network. | These | models are | called | physics- |
| --- | --- | --- | --- | --- | --- | --- | ---- | ------- | --- | ------ | -------- | ----- | ---------- | ------ | -------- |
Is transfer learning via trained model checkpoints feasible to reduce (PINNs).11,51–53
|     |     |     |     |     |     |     | informed |     | neural | networks |     |     | The | use of automatic |     |
| --- | --- | --- | --- | --- | --- | --- | -------- | --- | ------ | -------- | --- | --- | --- | ---------------- | --- |
trainingtimefornewsituations?
|         |          |          |        |              |          |         | differentiation |     | is  | not new | in CFD | and has | previously | been | used to |
| ------- | -------- | -------- | ------ | ------------ | -------- | ------- | --------------- | --- | --- | ------- | ------ | ------- | ---------- | ---- | ------- |
| In what | follows, | we first | review | the previous | progress | in deep |                 |     |     |         |        |         |            |      |         |
facilitatederivativecomputationinotherapplicationsoutsideofneural
neural model development for turbulent fluid simulation. Next, we networktraining.54–56
describethegeneralformofpartialdifferentialequationsthatgovern SomepapershavereportedtheuseofPDE-residual-drivenneural
turbulentflow(Sec.IIA),followedbyabriefexplanationofthearchi- models for turbulencestudies. A PINN architecture withRANS for-
tectureofthephysics-informedneuralnetworkandthetrainingstrate-
mulationhasbeenproposedtocalculatethemissingPDEparameters
gies (Sec. IIB). Section III shows the 3D turbulent wake simulation problem.57
|     |     |     |     |     |     |     | as  | an inverse |     |     | The zero-equation |     | turbulence | model | was |
| --- | --- | --- | --- | --- | --- | --- | --- | ---------- | --- | --- | ----------------- | --- | ---------- | ----- | --- |
aroundasinglewindturbineusingourPINNmodelandcomparison
usedtoincorporateRANSwithPINNmodelstosolvetheconjugate
withcomputationalfluiddynamics(CFD)solutionandfielddata.The
heattransferprobleminNVIDIASimNet.58RANSwasincorporated
computationalrequirementsandtheapplicabilityoftransferlearning
|            |               |     |            |          |           |            | into | the PINN  | models | by    | directly | predicting | unknown     | terms | in the    |
| ---------- | ------------- | --- | ---------- | -------- | --------- | ---------- | ---- | --------- | ------ | ----- | -------- | ---------- | ----------- | ----- | --------- |
| to improve | computational |     | efficiency | are also | discussed | (Sec. IV). |      |           |        |       |          |            |             |       |           |
|            |               |     |            |          |           |            | RANS | equations |        | using | data on  | the domain | boundaries, |       | including |
Finally,wediscussourfindingsandpresentconclusiveremarkswith Reynolds-stresscomponents,whichareobtainedfromnumericalsim-
futurework(Sec.V). ulations or experiments.59 A PINNs model for solving RANS equa-
|     |     |     |     |     |     |     | tions | showed | betterprediction |     | than | traditional | two-equation |     | models |
| --- | --- | --- | --- | --- | --- | --- | ----- | ------ | ---------------- | --- | ---- | ----------- | ------------ | --- | ------ |
A.Previousprogressindeepneuralmodelsfor forone-dimensionalRayleigh–Taylorturbulentmixingproblems.60A
turbulentflowsimulation PINN-basedsurrogatemodelforturbulentflowproblemsusingak–e
Wecategorizetheliteratureforturbulencemodelingusingneural RANSformulationwasdevelopedandpre-trainedusingdatafromtra-
networks (or machine learning in general) into two buckets: (i) ditionalsolversbeforeintroducingPDE-residuallossfortraining.61In
machine learning (ML)-augmented CFD methods and (ii) neural anotherPINNmodel,sparseDNSdatawereusedtogetherwithPDE-
models for flow simulation. In the second bucket, there are models residualloss.62Animprovementofdata-drivenTBNNwithinductive
trainedfrom CFD simulation data and those that are trainedwitha bias informed by turbulence realizability constraints, called physics-
informedTBNN,hasalsobeenproposed.63
targetofPDEresidual.
Withinthefirstbucket,theapproachesinML-augmentedCFD All the methods listed so far used simulation data for training
havemainlybeentomodeltheunknownReynoldsstresstensorinthe eitherfully(trackone)orpartially(tracktwo).Onemajorgoalofthe
RANS equation from mean velocity and pressure fields using presentpaperistodevelopaPINNmodeltosimulateturbulentflows
| Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 |     |     |     |     |     |     |     |     |     |     |     |     |     |     | 37,015110-2 |
| ------------------------------------------------ | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ----------- |
PublishedunderanexclusivelicensebyAIPPublishing

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
governed by steady-state RANS equations without using simulation B. PINNarchitecture
datafromtraditionalCFDsolvers.Thiswillreducethetrainingdata Letus denote eachequation inthe k(cid:1)e model [Eq.(1)]using
time,aswellasavoidusinghighperformancecomputingresourcesfor
thesetofgenericnonlinearfunctions
generatingsimulationdatafromtraditionalsolverssoastotrain the
newPINNmodels. f i ðu;xÞ¼0; x2X; (2a)
BðuðxÞÞ¼b; x2@X; (2b)
where i denotes different PDEs (continuity, momentum, k-transport
II. PINNMODELDEVELOPMENT ande-transportequation),Baretheboundaryand/orinitialcondition
A.ReynoldsaveragedNavierStokesturbulentflow
operator,x2XisthecoordinatesinthespatialdomainX,@Xisthe
equations
boundaryofthedomain,bistheboundaryconditionvalueandu2U
The Reynolds-averaged Navier–Stokes equations (RANS equa-
isthesolutionfieldinasolutionspaceUthatsatisfiestheabovePDE.
Thesolutionfielduconsistsoftheflowvelocities(u,vandw),pressure
tions)aretime-averagedequationsusedtomodelturbulentfluidflows. (p),turbulentkineticenergy(k),anddissipationrate(e).xdenotesthe
Theseequationsarederivedbydecomposingtheturbulentflowvaria-
coordinatesofthespatialdomain(x,y,z).
blesintomean(time-averaged)andfluctuatingparts,followedbytime
ThePINNapproachusesandtrainsaparameterizedneuralmodel
averaging.ThisapproachintroducesaReynolds-stressterms ij thatis HthatapproximatesthefunctionalmapbetweentheinputdomainX
modeledusingatwo-equationeddyviscosityturbulenceclosuremodel andthesolutiondomainU,i.e.,H:x(cid:3)h!7 u,wherehisthesetof
called the k(cid:1)e model. Specifically, the k(cid:1)e two-equation model
trainableweightsandbiases,suchthatdifferentialequationswiththeir
includestransportequationsforturbulentkineticenergy(k)andtur-
boundary condition are satisfied. Figure 1 shows the schematic of a
bulent dissipation rate (e).64The incompressiblesteady RANS equa-
PINNmodel.Afullyconnectedfeed-forwardneuralnetwork,enclosed
tions,withthetransportequationsfortheturbulentkineticenergy(k) inthebluebox,providestheoutput(u^;^v;w^;^p;^ k;^e)forthegiveninput
andthedissipationrate(e)intheCartesiancoordinates,aregivenas
variables (x, y, z). Thus, u^ðx;hÞ is the approximate solution of the
follows:
PDEsunderconsideration.Thepartialdifferentialtermsinthegovern-
@u
ingequations(e.g.,@u^=@xorhigher-orderterms)arecomputedusing
Continuity: @x i ¼0; (1a) automatic differentiation.To compute the boundary condition losses,
" i !# inthecaseoftheDirichletboundarycondition,theapproximatedout-
Momentum: @u i u j¼(cid:1) 1@p þ @ (cid:2) @u iþ @u j (cid:1) @s ijþS; putsarecomparedwiththeboundarydatadirectlyandtheautomatic
@x q@x @x @x @x @x i differentiationprocessisbypassed.IfNeumannconditionsarespecified
j i j j i j
attheboundary,thelossesarecomputedwiththehelpofautomaticdif-
! (1b) ferentiation.Theparameters(h)oftheneuralnetworkHarelearned
1 @u @u byminimizingalossfunctionL thatcomprisesthePDE-residual
Reynolds-stress: s ¼(cid:1)(cid:2) iþ j ; (1c) PINN
ij t2 @x @x lossandboundarydataloss,i.e.,
j i
" #
k-transport: @ku j¼ @ (cid:2) (cid:2)þ (cid:2) t (cid:3) @k þP (cid:1)e; (1d) L PINN ¼a b L 2boundary þa r L residual ; 3 (3a)
e-transpo @ rt x : j @ @ e x u @ j j x ¼ j @ @ x j "(cid:2) r (cid:2) k þ @ r (cid:2) x e t j (cid:3) @ @ x e j # k L bounda
1
ry " ¼ XN N
c
1 bp 4 X i N ¼ b 1 p ðBðu^ðx i ÞÞ(cid:1)bÞ25; (3b)
þC 1e k e P k (cid:1)C 2e e k 2 þSe ; (1e) L residual ¼ N c i¼1 a 1 ðf continuity Þ2þa 2 ðf momentu # m Þ2
(cid:2)
t
¼Cl k
e
2 ; (1f) þa 3 ðf k(cid:1)transport Þ2þa 4 ðfe(cid:1)transport Þ2 : (3c)
!
P ¼(cid:2) @u iþ @u j @u i; (1g) Here,a b istheweightingcoefficientforboundarylosses,a r istheweight-
k t @x @x @x ingcoefficientforresiduallosses,anda aretheweightingcoefficients
j i j 1(cid:1)4
assigned to the residuals of each governing PDE. A hyperparameter
where x i isthe spatialcoordinate, u i is the time-averaged velocity sweepisusedtofixthesecoefficients(seeAppendixB).N c represents
vector[u,wfor2Dinspace(x,z)andu,v,wfor3Dinspace(x,y, thetotalcountof locationpointswithinthedomainandN denotes
bp
z)], p is the mean pressure, (cid:2) is the kinematic viscosity, (cid:2) t is the thetotalnumberofboundarypoints.Theboundarylosstermisdeter-
turbulent viscosity, P k is the production of turbulent kinetic minedusingthemeansquarederrorwiththeboundarydataprovided.
energy, S i is the momentum source/sink term in the i direction, ThePDE-residuallossiscalculatedastheL2normoftheresidualsat
andSe isthesource/sinktermfordissipationrate.Forthe3Dtur- trainingpointscalculatedusingautomaticdifferentiation.Thetraining
bulentwakesimulationaroundasinglewindturbineunderneutral processisdominatedbythePDE-regularization.Therefore,trainingof
atmospheric conditions, the constant values are Cl¼0:033; r k PINNmodelscanbeseenasminimizingacombinationofasupervised
¼1:0;r e¼1:3; C 1e ¼1:176, and C 2e¼1:92, determined by losscalculatedfromtheboundaryconditionsandaunsupervisedlosscal-
regressionfitsofobservationdata.65 culatedfromtheresidualofthePDEsbyautomaticdifferentiation.
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-3
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

| Physics | of Fluids |     |     |     |     |     |     | ARTICLE |     | pubs.aip.org/aip/pof |     |     |     |
| ------- | --------- | --- | --- | --- | --- | --- | --- | ------- | --- | -------------------- | --- | --- | --- |
FIG.1.SchematicofaPINNmodelfor3DRANSsimulation.ThePINNmodelisafullyconnectedfeed-forwarddenseneuralnetworkshownintheblueenclosure.Theloss
calculationthroughautomaticdifferentiationisvisualizedasdottedconnectionsintheredenclosure.Twolossesarecalculated(i)partialdifferentialequation(PDE)residual
lossand(ii)boundarycondition(BC)loss.
C.Wallfunctions models yield improved outcomes with a smaller number of hidden
layers.71Traininghyperparameters,includingthenumberofneurons
Thestandardmodelk(cid:1)eisreliableforapplicationswithahigh
 12 September 2026 13:02:35
Reynolds number that do not have flow separation and reattach- ineachlayerusedtomodelasinglewindturbinearechosenbyrepeti-
Biases72
ment.66In such casescommonly encounteredin industrial flow sce- tive experiments tracked with Weights and (Table I). Swish
activationisusedforallhiddenlayers,73ReLUactivationisusedfor
| narios, the | use of wall | functions | is preferred | to achieve |     | sufficiently |     |     |     |     |     |     |     |
| ----------- | ----------- | --------- | ------------ | ---------- | --- | ------------ | --- | --- | --- | --- | --- | --- | --- |
precisesimulations.67Inconventionalnumericalmethods,wallfunc- the output nodes corresponding to turbulent kinetic energy (k) and
dissipationrate(e)toavoidnegativeoutputs,andnoactivationisused
| tions reduce | computational | cost | by avoiding | the need | for | fine grids. |               |        |             |           |             |                |     |
| ------------ | ------------- | ---- | ----------- | -------- | --- | ----------- | ------------- | ------ | ----------- | --------- | ----------- | -------------- | --- |
|              |               |      |             |          |     |             | for the other | output | nodes. Adam | optimizer | is utilized | to iteratively |     |
Placingthefirstnodepointsufficientlyfarintheoverlapregionofthe
|     |     |     |     |     |     |     | find the | model | parameters while | training for | a preset | number | of  |
| --- | --- | --- | --- | --- | --- | --- | -------- | ----- | ---------------- | ------------ | -------- | ------ | --- |
turbulentboundarylayerleadstoasignificantreductioninthenumber
epochswithexponentiallydecayinglearningratesstartingwith0.0001.
ofcellsnearthewallorboundary.68Wallfunctionstakeadvantageof
Adamisafirst-orderoptimizerbasedonanadaptivegradientdescent
theuniversalityexhibitedbytheprofilesnearthewallathighReynolds
|           |                 |           |             |            |        |           | with momentum.74 |            | For parameter | initialization,       | the | Glorot uniform |        |
| --------- | --------------- | --------- | ----------- | ---------- | ------ | --------- | ---------------- | ---------- | ------------- | --------------------- | --- | -------------- | ------ |
| numbers.  | The logarithmic | law       | of the wall | is applied | in the | overlap   |                  |            |               |                       |     |                |        |
|           |                 |           |             |            |        |           | initializer      | is used.75 | Mini-Batch    | training is performed |     | because        | of the |
| region to | obtain the      | mean flow | quantities  | parallel   | to     | the wall. |                  |            |               |                       |     |                |        |
largenumberofcollocationpointsnecessaryforthe3Dwakesimula-
Moreover,thewallfunctionapproachallowstheinclusionofempirical
informationinspecialcases,suchasinroughwallconditions.69 tion. Training is carried out on a standalone workstation with two
NVIDIARTXA6000GPUs.Thecode,themodelarchitecture,andthe
WeusewallfunctionsinEq.(3b)toensurethatourPINNmodel trainedweightshavebeenreleasedonGitHubwithaZenodoDOI.76
| satisfies the | flow profile | near the | wall. | Unlike traditional |     | CFD, the |                 |     |              |               |           |       |     |
| ------------- | ------------ | -------- | ----- | ------------------ | --- | -------- | --------------- | --- | ------------ | ------------- | --------- | ----- | --- |
|               |              |          |       |                    |     |          | The pseudo-code |     | for training | the developed | RANS-PINN | model | is  |
trainingofthePINNmodeldependsongradientdescent-basedopti-
showninTableII.
mizationinalosslandscapeformedbythecombinationofPDElosses
andboundarylosses.Hence,thereisapossibilitythatthesolutioncan
| get stuck | in local minima | or  | move toward | a non-desired |     | solution. |     |     |     |     |     |     |     |
| --------- | --------------- | --- | ----------- | ------------- | --- | --------- | --- | --- | --- | --- | --- | --- | --- |
TABLEI.Hyperparametersusedforsinglewindturbinemodeling.
Providingthemeanflowquantitiesusingthewallfunctionsdrivesour
| PINN model | toward the | correct | solution | quickly. | There | are many |     |     |     |     |     |     |     |
| ---------- | ---------- | ------- | -------- | -------- | ----- | -------- | --- | --- | --- | --- | --- | --- | --- |
applicationswherethefocusisnotonresolvingtheunderlyingphysics Neurons(hiddenlayers) 600
intheboundarylayer.Insuchcases,wallfunctionshelptominimize Neurons(outputlayer) 500
| theneedforahighnumberofsamplepoints. |     |     |     |     |     |     | Learningrate |     |     |     |     | 0.0001 |     |
| ------------------------------------ | --- | --- | --- | --- | --- | --- | ------------ | --- | --- | --- | --- | ------ | --- |
|                                      |     |     |     |     |     |     | Epochs       |     |     |     |     | 25000  |     |
| D.Implementation                     |     |     |     |     |     |     | Optimizer    |     |     |     |     | Adam   |     |
The PINN model above is implemented using the TensorFlow Trainable-parameters 2890200
package.70
software The architecture has two/three inputs (corre- Batches 12
spondingto2D/3Dapplications),five/sixoutputs(2D/3D),fourhid- Activationfunction SwishþReLU
den layers that are shared by all outputs, and a separate additional Initializer Glorotuniform
layerforeachoutput(Fig.1).OurpreviousstudyshowedthatPINN
| Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 |     |     |     |     |     |     |     |     |     |     |     | 37,015110-4 |     |
| ------------------------------------------------ | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ----------- | --- |
PublishedunderanexclusivelicensebyAIPPublishing

| Physics | of Fluids |     |     |     |     |     | ARTICLE | pubs.aip.org/aip/pof |     |     |
| ------- | --------- | --- | --- | --- | --- | --- | ------- | -------------------- | --- | --- |
TABLEII.Pseudo-code:RANS-PINNimplementation.
C DþB;C(cid:1)Setofcollocationpoints;D(cid:1)Setofdomainpoints;B(cid:1)Setofboundarypoints
| train_PINN:Randomlyinitializeweightsw |     |     |     | ¼fw ;w ;…;w |     |     |     |     |     |     |
| ------------------------------------- | --- | --- | --- | ----------- | --- | --- | --- | --- | --- | --- |
|                                       |     |     |     | i 1 2       | ng  |     |     |     |     |     |
whileEpochs<Total
|     |     | stepsdoforward | pass |     |     |     |     |     |     |     |
| --- | --- | -------------- | ---- | --- | --- | --- | --- | --- | --- | --- |
inputx¼fx;y;zgintheinputlayer,x2C
output¼fu;v;w;p;k;(cid:3)gintheoutputlayer
Loss 0
GetPDElosses
UseautomaticdifferentiationtocalculatethederivativesusedinthePDEs.
SolveEq.(1).
1.Calculate(cid:2)
[Eq.(1f)].
t
| 2.Calculates |     | andP | [Eqs.(1c)and(1g)]. |     |     |     |     |     |     |     |
| ------------ | --- | ---- | ------------------ | --- | --- | --- | --- | --- | --- | --- |
|              |     | ij   | k                  |     |     |     |     |     |     |     |
3.PDE Loss¼residualsofcontinuity,momentum,k-transportand(cid:3)-transportequations[Eqs.(1a),(1b),(1d),and(1e)].
| Lossþ¼PDE |     | Loss |     |     |     |     |     |     |     |     |
| --------- | --- | ---- | --- | --- | --- | --- | --- | --- | --- | --- |
ifxisinBthengetBoundaryConditionloss
DirichletBoundary:Calculatetheresidualsusingtheboundaryvalues.
NeumannBoundary:UseAutomaticDifferentiationtocalculatethederivativesandcalculatetheresidualsusingtheboundary
values.
Lossþ¼BC Loss
endif
UsetheLosstocalculatethegradientsandupdatetheweights.
endwhile
 12 September 2026 13:02:35
E.2Dmodeldevelopment Thefieldandnumericalsolverdatasetsfortheturbinecasesaredis-
Before simulating the 3D turbulent wake, two benchmark test cussedin Sec. IIIC. Section IIIDshows aconvergencestudy for the
PINNmodelfollowedbythewakesimulationsinSec.IIIE.
casesaresimulatedinthe2Dspatialdomaintoverifyourimplementa-
| tion and validate | the | consistency | of our PINN | model. The | first test |     |     |     |     |     |
| ----------------- | --- | ----------- | ----------- | ---------- | ---------- | --- | --- | --- | --- | --- |
A.Actuatordiskmodelsourceterms
caseisthesimulationofaturbulentflowdrivenbyapressuregradient
ina2Dchannel.ThesolutionobtainedfromourPINNmodeliscom- TheactuatordiskmodelprovidesthesourcetermsS andSetobe
i
pared with the solution of DNS and RANS simulations from tradi- usedintheRANSgoverningequationsintheregionaroundthewind
tionalCFDtools.DNSsimulationdataofturbulentchannelflowfor turbine. The momentum source term (S) in Eq. (1b) imposes the
i
frictionReynoldsnumbersof180,395,and590areusedfromtheliter-
thrustforcesontheflow,whichisdistributedintheregionrepresent-
ature.77,78Asimplein-housefinite-volumecodeinMATLABisused
ingtheactuatordisk.Theequationforthrustexerted(T)andpower
to obtain the RANS CFD data. The second test case simulates a extracted(P)bythediskaregivenby
streamwisehomogeneousflowdrivenbyvelocity.Forthiscase,theref-
1
erencevelocityandturbulentquantityprofilesoftheneutralstratified T ¼ qC A u2; (4)
T d 0
atmosphericboundarylayer(ABL)flowfromtheliteratureareused.79 2
| Both these | test cases | are simulated | using | the 2D formulation | of the |     |     |     |     |     |
| ---------- | ---------- | ------------- | ----- | ------------------ | ------ | --- | --- | --- | --- | --- |
1
governing PDEs Eq. (1) without any source term (Sec. IIA). Using P¼ qC A u3 ; (5)
2 P d o
| these flow | scenarios, | we also | fine-tune | the hyperparameters |     |     |     |     |     |     |
| ---------- | ---------- | ------- | --------- | ------------------- | --- | --- | --- | --- | --- | --- |
a ;a ;a ;a ;a ,anda whereC isthethrustcoefficient,C isthepowercoefficient,A
| b r 1                                                  | 2 3 | 4 inEq.(3).(SeeAppendixAfordetailsonthe |     |     |                | T       |           | P                     |                   | d      |
| ------------------------------------------------------ | --- | --------------------------------------- | --- | --- | -------------- | ------- | --------- | --------------------- | ----------------- | ------ |
|                                                        |     |                                         |     |     | is the         | area of | the disk, | and u is the upstream | velocity.         | C is a |
| 2DflowsimulationsandAppendixBforhyperparametertuning.) |     |                                         |     |     |                |         |           | 0                     |                   | T      |
|                                                        |     |                                         |     |     | nondimensional |         | number    | that describes        | the force exerted | by the |
III.3DTURBULENTFLOWBEHINDAWINDTURBINE
turbineintheaxialdirectionontheincomingmomentumofthe
ThePINNmodelisutilizedtoforecastthewakegeneratedbya flow,andC isdefinedasthe fractionofthepowerextractedby
P
singlewindturbine.Thiswakeoccursduetotheobstructioncreated the wind turbine relative to the energy available in the wind
bythe windturbine as it disruptsthe incomingairflow. The turbine stream. For a wind turbine, the thrust and power coefficient are
itselfisrepresentedusinganactuatordiskmodel80,81andisincorpo- providedbythemanufacturer.Theyareusedtomodeltheeffect
rated into the k(cid:1)eRANS model as a source term (Sec. IIIA). The of all individual components of the wind turbine, such as blade
domainandexperimentalsetuparediscussedinSec.IIIB.Forthepur- shapes,structuralproperties,andgeneratorandgearboxcharac-
poseofnumericalsimulations,thewakeiscomputedfortwoseparate teristics.Inthepresentwork,thethrustforcerepresentedbyEq.
standalonewindturbines,namely,theSexbierumHOLECWPS30/3 (4) is averaged by the turbine area and is normally distributed
Wind Turbine and the three-blade 630-kW Nibe-B wind turbine. alongthestreamwisedirectionusingthesourcetermgivenas
| Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 |     |     |     |     |     |     |     |     |     | 37,015110-5 |
| ------------------------------------------------ | --- | --- | --- | --- | --- | --- | --- | --- | --- | ----------- |
PublishedunderanexclusivelicensebyAIPPublishing

| Physics | of Fluids |     |     |     |     |     | ARTICLE |     | pubs.aip.org/aip/pof |     |     |     |
| ------- | --------- | --- | --- | --- | --- | --- | ------- | --- | -------------------- | --- | --- | --- |
 12 September 2026 13:02:35
FIG.2.Schematicofthesinglewindturbinemodelingdomain:(a)lateralview,(b)frontview,and(c)topview.DisthediameteroftheturbineandHisthehubheight.The
boundaryconditionsusedonthedomainsurfacesarealsoshown.
1
qC u2; thedomainpointsatwhichthePDE-residualloss[Eq.(3c)]isimposed
S i ¼(cid:1) T (6) aresampledusingHammersleysampling.84,85Theregiondownstream
2
ofthewindturbinecanbedividedintotwo:nearwakeandfarwake.86
| where u represents | the far upstream |     | velocity or | the rotor | averaged |           |               |             |       |              |      |        |
| ------------------ | ---------------- | --- | ----------- | --------- | -------- | --------- | ------------- | ----------- | ----- | ------------ | ---- | ------ |
|                    |                  |     |             |           |          | To obtain | accurate wake | simulations | using | the actuator | disk | model, |
velocitybasedonwhichthethrustcoefficientiscorrelated.Thenega-
|     |     |     |     |     |     | the source | terms are applied | in  | a cylindrical | region | with a | diameter |
| --- | --- | --- | --- | --- | --- | ---------- | ----------------- | --- | ------------- | ------ | ------ | -------- |
tivesignindicatesthatthethrustisappliedtotheincomingfloworS
i equaltotheturbinediameter(D)andalengthof0.25Dupstreamand
isasink/negativesourceterm.Althoughthestandardk(cid:1)emodelfor
downstreamofthedisk.83Thehighlyheterogeneousnearwakecharac-
| the RANS | closure with the | momentum | source term | can predict | the |     |     |     |     |     |     |     |
| -------- | ---------------- | -------- | ----------- | ----------- | --- | --- | --- | --- | --- | --- | --- | --- |
terizesacomplexflowdistributionextendingtoadistanceof2to4D
| presence of | the disk, some | flow variables | are highly | overestimated. |     |     |     |     |     |     |     |     |
| ----------- | -------------- | -------------- | ---------- | -------------- | --- | --- | --- | --- | --- | --- | --- | --- |
(rotordiameter)downstream.Itisstronglyinfluencedbythedesignof
Thus, an additional term that represents the rate of energy transfer blades.87,88
|     |     |     |     |     |     | the rotor | and the aerodynamic |     | properties | of the |     | In this |
| --- | --- | --- | --- | --- | --- | --------- | ------------------- | --- | ---------- | ------ | --- | ------- |
fromlarge-scaleturbulencetosmall-scaleturbulencecontrolledbythe
|     |     |     |     |     |     | study, to | precisely capture | the behavior |     | of the near-wake |     | flow, the |
| --- | --- | --- | --- | --- | --- | --------- | ----------------- | ------------ | --- | ---------------- | --- | --------- |
productionrangescaleandthedissipationratetimescaleisusedinthe
|                                                                  |     |     |     |     |     | domain    | training points are | increased | in     | the cylindrical | region | with     |
| ---------------------------------------------------------------- | --- | --- | --- | --- | --- | --------- | ------------------- | --------- | ------ | --------------- | ------ | -------- |
| e(cid:1)transportequation[Eq.(1e)]toimprovethesimulation.82,83Se |     |     |     |     | is  |           |                     |           |        |                 |        |          |
|                                                                  |     |     |     |     |     | length¼6D | and diameter¼2D,    |           | placed | symmetrically   | to     | the disk |
definedasfollows:
(refinedregioninFig.2).Thisprocessisinspiredbythemeshrefine-
P2 mentusedintraditionalnumericalsolvers.Inthefarwakeregion,the
k;
Se ¼C 4eqk (7) turbine’s influence is restricted to the thrust force and the turbulent
kineticenergy.Thus,asmallernumberofsamplingpointsissufficient
whereC isaconstantwhosevalueissetto0.37(fromthereported comparedtothenear-wakeregion.
4e
experimentaldata83),P
k istheproductionofturbulentkineticenergy,
andkistheturbulentkineticenergy.Notethattheuseofsourceterms
isrestrictedonlytotheactuatordiskregion. TABLEIII.Windturbineandflowspecifications.
|                     |     |     |     |     |     | Windturbine |     | D(m)H(m)U |     | ðm=sÞTI |     | ð%Þ C |
| ------------------- | --- | --- | --- | --- | --- | ----------- | --- | --------- | --- | ------- | --- | ----- |
| B.Domainandtraining |     |     |     |     |     |             |     |           |     | ref     | ref | T     |
Figure2showstheschematicofthedomain.Duringtrainingof SexbierumHOLECWPS30/3 30.1 35 10 10 0.75
the PINN model, the boundary points at which boundary loss Nibe-Bwindturbine 40 45 8.5 10 0.82
| [Eq.(3b)] is                                     | imposed aresampled | using | a grid-based | approach, | and |     |     |     |     |     |             |     |
| ------------------------------------------------ | ------------------ | ----- | ------------ | --------- | --- | --- | --- | --- | --- | --- | ----------- | --- |
| Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 |                    |       |              |           |     |     |     |     |     |     | 37,015110-6 |     |
PublishedunderanexclusivelicensebyAIPPublishing

| Physics | of Fluids |     |     |     |     |     | ARTICLE |     |     | pubs.aip.org/aip/pof |     |
| ------- | --------- | --- | --- | --- | --- | --- | ------- | --- | --- | -------------------- | --- |
 12 September 2026 13:02:35
FIG.3.Comparisonof(a)velocityand(b)turbulentkineticenergypredictedbyPINNmodelforavaryingnumberofsamplepointswithRANS-CFDsimulationat2.5D,5.5D,
and8DdownstreamtheSexbierumHOLECWPS30/3windturbine.
Fullydevelopedinletprofilesarespecifiedattheinletboundary u 2 sffiffiffiffiffi;
|     |     |     |     |     |     |     |     |     | k¼p | ffi | (8b) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---- |
for mean velocity [Eq.(8a)], turbulent kinetic energy [Eq. (8b)] and Cl
turbulentdissipationrate[Eq.(8c)]asfollows:79
u3
|     |     |     | (cid:2) | (cid:3) |     |     |     | e¼  |     | s ; |     |
| --- | --- | --- | ------- | ------- | --- | --- | --- | --- | --- | --- | --- |
jðzþz (8c)
|     |     |     | us zþz | 0 ; |      |          |                                 |     |     | Þ   |                       |
| --- | --- | --- | ------ | --- | ---- | -------- | ------------------------------- | --- | --- | --- | --------------------- |
|     |     | u¼  | ln     |     | (8a) |          | qffiffiffiffi                   |     |     | 0   |                       |
|     |     |     | j z    |     |      |          |                                 |     |     |     |                       |
|     |     |     |        | 0   |      |          | s qwisthefrictionvelocity(withs |     |     |     |                       |
|     |     |     |        |     |      | whereus¼ |                                 |     |     |     | isthewallshearstress, |
w
andqisthefluiddensity),j(cid:4)0:418isthevonK(cid:2)arm(cid:2)anconstant,zis
|     |     |     |     |     |     | the height | co-ordinate, | and | z is the | aerodynamic | roughness height. |
| --- | --- | --- | --- | --- | --- | ---------- | ------------ | --- | -------- | ----------- | ----------------- |
0
TABLEIV.ComputationaltimeforPINNmodelforsingleturbinewakesimulationfor Inletprofiles[Eq.(8)]areanalyticalsolutionsofthemomentumand
differentbasesizes. k(cid:1)emodelequations.89Attheoutlet,aprovidedpressureboundary
conditionandzerogradientsalongthestreamwisedirectionforother
base_size Timefor1000epochs(min) quantitiesareimposed.Atthebottomwall/ground,wallfunctionscon-
|     |     |     |     |     |     | sistent | withthe inlet | profiles | are usedtospecifyDirichletconditions |     |     |
| --- | --- | --- | --- | --- | --- | ------- | ------------- | -------- | ------------------------------------ | --- | --- |
1 70 forvelocity,turbulentkineticenergy,anddissipationrate.Thetopface
|     | 2   |     |     | 91  |     |     |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
andadditionallateralfacesinthe3Ddomainareprovidedwithsym-
3 112 metryboundaryconditionswithazerovelocitynormaltotheface.
|     | 4   |     |     | 132 |     | Weperformsimulationsfortwoseparatestand-alonewindtur- |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | ----------------------------------------------------- | --- | --- | --- | --- | --- |
5 156 bines, the HOLECWPS 30/3 Wind Turbine from Sexbierum, and a
three-blade630-kWNibe-Bwindturbine.TheHOLECWPS30/3WT
| Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 |     |     |     |     |     |     |     |     |     |     | 37,015110-7 |
| ------------------------------------------------ | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ----------- |
PublishedunderanexclusivelicensebyAIPPublishing

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
FIG.4.(a)Boundaryand(b)PDElossofthePINNmodelforavaryingnumberofsamplepoints.
hasadiameterD¼30.1mandahubheightH¼35m.Theboundary TableIIIsummarizesthewindturbineandflowspecifications.Foreach
conditionsaresetforafreestreamwindspeedof10m/swithaturbu- simulation,thePINNmodelistrainedfromscratch.
lenceintensityof10%atthehubheight.Athrustcoefficientof0.75cor-
respondingtotheseconditionsisalsoused.TheNibewindturbine“B” C.DatafromfieldandconventionalCFD
has a diameter D¼40 m and a hub height H¼45 m. Here, a free The validation of the PINN model with the turbulence clo-
stream wind speed of 8.5m/s and turbulence intensity of 10% at the suresandABLinflowequationswasperformedusingthefieldand
hub height were used with a corresponding thrust coefficient of 0.82. numerical solver data sets for the standalone Sexbierum90 and
FIG.5.Contoursof(a)velocity,(b)turbulenceintensity,and(c)pressureonahorizontalplaneathubheightfortheSexbierumHOLECWPS30/3windturbine.Solidblackline
representsthepositionoftheturbine.Aquantitativecomparisonismadeatadistanceof2.5D,5.5D,and8Ddownstreamoftheturbine.
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-8
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
FIG.6.Comparisonof(a)velocityand(b)turbulentkineticenergypredictedbyPINNmodelwithdatafromexperimentandnumericalsolversat2.5D,5.5D,and8Ddown-
streamtheSexbierumHOLECWPS30/3windturbine.
Nibe91 wind turbines. The single wake measurement dataset from PDE-residual loss is imposed. Here, a study is done to analyze the
theSexbierumturbinecontainsthenormalizedvelocityandturbu- dependencyonthenumberofsamplingpointsandtheconvergenceof
lentkineticenergybehindasinglewindturbineatdistancesof2.5, thePINNmodel.Thenumberofsamplingpointsischosensuchthat
5.5, and 8 turbine diameters. The data reported corresponding to base size(cid:3)104pointsareusedforthewholedomain,base size(cid:3)103
theNibe-Bwindturbineoperatingaloneconsistsofthemeasure- pointsareusedfortherefinedregion,andbase size(cid:3)103areusedfor
mentsof normalizedvelocityandturbulence intensitybehindthe the actuatordiskregion.Wevarythe basesizefrom1to 5to study
turbine at distances of 2.5, 4, and 7.5 turbine diameters. The convergence.Figure3showsthesimulationofthewakebehindasin-
numericalsimulationusingthefinitevolumemethodisperformed glewindturbineoftheSexbierumwindfarmfordifferentbasesizes.
using the Simcenter STAR-CCMþ software package.92 Different The SST k(cid:1)x numerical simulation using the Simcenter STAR-
turbulence models, namely standard k(cid:1)e,64 standard k(cid:1)x,93 CCMþ atdownstreamdistancesof2.5,5.5,and8turbinediameters
shear stress transport (SST) k(cid:1)x,94 and Reynolds stress model arealsoprovidedtoshowhowthePINNmodelisabletocapturethe
(RSM)95,96 were implemented using STAR-CCMþ. An appropri- variationsindifferentflowparameters.TheSSTk–xmodelisaneffec-
atemeshsizeischosenbyperformingameshconvergenceanalysis tiveturbulencemodelforthewindturbinesimulations.97Allsimula-
toreducespatialdiscretizationerrorsintheCFDsimulationsand tionscapturethetrendsinvelocityandturbulentkineticenergy(TKE)
toguaranteeamesh-independentsolution(AppendixC). variationinthenear-downstream(2.5D)well.However,movingfur-
therdownstream,thevelocityrecoveryislessinsimulationswithbase
sizesof1,2,and3.Forbasesizes4andabove,thesimulationshows
D.ConvergenceofPINNmodelwithnumberof
good agreement with the experimental data even in the far down-
samplingpoints
stream.TheTKEalsoshowsasimilartrend.Theincreaseinbasesize
InthePINNmodel,theaccuracyofthetrainingdependsonthe from4to5gaveabarelynoticeableimprovementinthesimulations,
numberofrandomlysampledpointswithinthedomainatwhichthe especially considering the velocity plots. A detectable change in the
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-9
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
FIG.7.Contoursof(a)velocity,(b)turbulenceintensity,and(c)pressureonahorizontalplaneathubheightfortheNibe-Bwindturbine.Solidblacklinerepresentstheposition
oftheturbine.Aquantitativecomparisonismadeatadistanceof2.5D,4D,and7.5Ddownstreamoftheturbine.
simulation is observed only in the near downstream TKE. However, turbulencemodelsandthePINNmodelbycomparingwiththeexperi-
this gain is shadowed by the increasing computational cost with the mentaldata.Also,thePINNmodelsimulationiscomparedwiththe
basesizewhentrainingthemodelforhigherepochs.TableIVliststhe numerical solvers to assess the performance of PINN model. The
computational time for different base sizes. The simulation conver- RMSEfornormalizedvelocityandTKEfortheSexbierumwindtur-
gencedoesnotexhibitaproportionalrelationshipwiththeincreasein binearereportedinTableV,andtheRMSEfornormalizedvelocity
the base size. Meanwhile, mesh sensitivity analysis of the numerical andturbulenceintensityforNibewindturbinearereportedinTable
simulationusingthefinitevolumemethodshowsthatasthemeshsize VI.ThesimulationsfromnumericalsolversandPINNmodelarefur-
isreduced,thesimulationisbetter(seeAppendixC).Duringtraining, therevaluatedbyplottingtheabsolutedifferencebetweenthesimula-
itisobservedthatPDEphysicsislearnedbetter(lowerresidualerror
tionsandtheexperimentaldata90,91(Figs.9and10).Thefiguresshow
of PDE)with an increasing numberof samplesas expected (Fig. 4). that the PINN simulation closely follows the variation and values
The loss curves also show no improvement with an increase in the
exhibitedbytheSSTk–xmodelcomparedtoothernumericalmodels.
basesizefrom4to5.
Also,astudyondifferentturbulencemodelsconcludesthattheSSTk–
x model is an effective turbulence model for wind turbine simula-
tions.97Hence,anabsolutedifferenceplot(Figs.11and12)between
E.WakesimulationsfromthetrainedPINNmodel the simulations from the PINN model and the SST k–x numerical
Figure 5 shows the contour plot of the RANS-PINN turbulent solver is shown to compare the developed model against the best
flow simulations (velocity, turbulence intensity and pressure), and numericalmodel.ThefiguresshowthatthedevelopedPINNmodelis
Fig. 6 shows the normalized velocity and Turbulent Kinetic Energy abletogiveresultsonparwiththeSSTk–xmodel.TheRMSEvalues
profiles at three locations (2.5D, 5.5D, and 8D) downstream of the (comparisonwithPINNinTableVandVI)substantiatethattheper-
Sexbierumturbine.Inthelatterfigure,datafromthefieldandconven- formanceofthePINNmodelissimilartotheSSTk–xmodelcom-
tional CFD simulations are shown for comparison. Figures 7 and paredtoothernumericalmodels.
8 show the same for the Nibe turbine. Root-mean square errors Inthecontourplots(Figs.5and7),thewakecreatedbytheturbine
(RMSE) were calculated for the simulation results from different is evident from the low velocity (panel a) and low pressure (panel c)
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-10
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
FIG.8.Comparisonof(a)velocityand(b)turbulenceintensitypredictedbyPINNmodelwithdatafromexperimentandnumericalsolversat2.4D,and7.5Ddownstreamthe
Nibe-Bwindturbine.
regions downstream of the turbine. This causes turbulent transport of disk edges which is an indication of vortex formation immediately
momentumfromtheambientwindintothewakeregionasseeninthe behindtherotorbladetips(markedbynumeralI).Furtherdownstream,
turbulenceintensitycontourplot(panelb).Thewindturbinegenerates ashearlayerisformedandenclosesthewake(markedbynumeralII).
turbulenceinadditiontothatalreadyproducedbytheterrain,indicated ThefarwakeregionisalsowellpredictedbythePINNmodel.Itisindi-
bytheincreasedturbulenceintensitybehindtheturbine.Itisalsoevident catedbytheexpansionoftheshearlayertothecenterbyturbulentdiffu-
that the turbulence intensity has a sharp structure emerging from the sion(markedbynumeralIII).Theaxisymmetricnatureofthewakeseen
TABLEV.RMSEbetweentheexperimentaldataandthesimulationsresultsfromdifferentturbulencemodelsandPINNfortheSexbierumHOLECWPS30/3windturbine.
NormalizedvelocityandTKEarecomparedat2.5D,5.5D,and8Ddownstreamoftheturbine.
Comparisonwithexp.data ComparisonwithPINN
Quantiy Distance k–(cid:3) k–x SSTk–x RSM PINN k–(cid:3) k–x SSTk–x RSM
Normalizedvelocity 2.5D 0.1899 0.1975 0.0958 0.0782 0.0768 0.1448 0.1517 0.0232 0.0308
5.5D 0.0749 0.0808 0.0488 0.0475 0.0433 0.0651 0.0711 0.0138 0.0217
8D 0.0587 0.0662 0.0522 0.0458 0.0406 0.038 0.0441 0.0140 0.009
NormalizedTKE 2.5D 0.0115 0.0118 0.0151 0.0154 0.0170 0.0133 0.0131 0.0032 0.0038
5.5D 0.0044 0.0044 0.0058 0.0047 0.0062 0.0031 0.0029 0.0022 0.0024
8D 0.0045 0.0045 0.0039 0.0039 0.0047 0.0024 0.0024 0.0017 0.0021
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-11
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
TABLEVI.RMSEbetweentheexperimentaldataandthesimulationsresultsfromdifferentturbulencemodelsandPINNfortheNibe-Bwindturbine.Normalizedvelocityandtur-
bulenceintensityarecomparedat2.5D,4D,and7.5Ddownstreamoftheturbine.
Comparisonwithexp.data ComparisonwithPINN
Quantiy Distance k–(cid:3) k–x SSTk–x RSM PINN k–(cid:3) k–x SSTk–x RSM
Normalizedvelocity 2.5D 0.1841 0.1925 0.0620 0.0492 0.0666 0.1373 0.1454 0.0190 0.0581
4D 0.0691 0.0741 0.0629 0.0789 0.0503 0.0773 0.0845 0.0314 0.0529
7.5D 0.0459 0.0477 0.0509 0.0445 0.0488 0.0253 0.0322 0.0330 0.0245
Turbulenceintensity(%) 2.5D 0.0301 0.0298 0.0193 0.0143 0.0277 0.0468 0.0462 0.0201 0.0263
4D 0.0233 0.0233 0.0139 0.0179 0.0184 0.0329 0.0327 0.0175 0.0279
7.5D 0.0195 0.0195 0.0130 0.0187 0.0169 0.0260 0.0262 0.0181 0.0253
inthecontourplotsisaresultoftheRANSclosurebeingusedforthe indication of the thrust force exerted by the turbine on the incoming
simulations.TheRANSturbulenceclosurefailstosimulatehighlytran- flow.Ahigherpressurejumpindicatesalargerthrustforce.
sientfinevortextubes,whichinturnobstructthedevelopmentofcom- Comparison with experimental data and numerical solutions is
plexvortexstructures,andthesimulatedvortextubemovesinastraight performedtovalidateourPINNmodelatthreedownstreamlocations
linewithoutmeandering.Thepressurejumpacrossthediskisseenfrom of the wind turbine at a distance of 2.5D, 5.5D, and 8D for the
the pressure contours (marked by numeral IV), which is also an Sexbierumwindturbine.Figure6(a)showsthenormalizedwindspeed
FIG.9.Absolutedifferenceof(a)velocityand(b)turbulentkineticenergybetweentheexperimentaldataandthesimulationsresultsfromdifferentturbulencemodelsandPINN
at2.5D,5.5D,and8DdownstreamtheSexbierumHOLECWPS30/3windturbine.
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-12
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
FIG.10.Absolutedifferenceof(a)velocityand(b)turbulenceintensitybetweentheexperimentaldataandthesimulationsresultsfromdifferentturbulencemodelsandPINNat
2.5D,4D,and7.5DdownstreamtheNibe-Bwindturbine.
downstreamofthewindturbineasafunctionofthewinddirection. Similar results are obtained for the Nibe turbine (Fig. 8). The
Winddirectionindicatestheanglebetweenalinepassingthroughthe velocityandturbulenceintensityarecomparedwiththeexperimental
centeroftheturbineatthehubheight,andthelinejoiningthecenter data and conventional CFD simulations at locations 2.5D, 4D, and
oftheturbinewithalineparalleltotheturbine,wheremeasurements 7.5Ddownstreamoftheturbine.SimilartotheSexbierumturbinesim-
aretakenatthespecifieddownstreamdistances,asmarkedinthecon- ulations,herealso,thevelocityplots[Fig.8(a)]showthatthesimula-
tourplot[Fig.5(a)].Themaximumwindspeeddeficitisobservedin tionresultsagreewellwiththeexperimentandtheresultsoftheSST
the direction behind the center of the turbine (zero degrees) as k(cid:1)xandRSMmodels.Figure8(b)showsthattheturbulenceinten-
expected.Itcanbeseenthatthewindspeedpredicteddownstreamis sityformsaplateaudownstreamoftheturbine,whichflattensfurther
ingoodagreementwiththeexperimentaldata.Inaddition,theaccu- downstreamandfollowsthetrendexhibitedbytheexperimentaldata.
racyofthevelocityprofilesfromthePINNmodeliscomparabletothe Theturbulenceintensityisunder-predictedfardownstream.Although
RSM and SST k(cid:1)x models. The RSM and SST k(cid:1)x models are theTKEandturbulenceintensityprofilesshowsomedeviationfrom
computationallyintensivebutaremoreaccuratecomparedtothestan- theCFDsimulation,thevelocityprofilesagreewell.Amajoruseofthe
dardk(cid:1)eandk(cid:1)xmodels.Figure6(b)showsthenormalizedtur-
turbulent wake simulations is to estimate the power output from a
bulentkineticenergyatthreedownstreamlocations.Inthenear-wake wind farm where other turbines will be placed in the downstream.
region(2.5D),thePINNmodelisabletopredictthepeaksofTKEgen-
Velocityisthemostcriticalinputtoestimatingpower[Eq.(5)],and
eratedbythetipvorticessimilartotheSSTk(cid:1)xandRSMmodels.
thus,anaccurateestimateofthevelocityiscrucial.
However,thestandardk(cid:1)eandk(cid:1)xwithbaselinecoefficientswere
unabletocapturethesame.Furtherdownstream(5.5D),theTKEpro-
IV. COMPUTATIONALTIME
filesexhibitamoreflatpeak.AlthoughtheTKEisslightlyunderesti-
matedinthefardownstreamregion(8D),overall,thePINNmodels Forallcases,trainingisperformedonastandaloneworkstation
providesimulationsthatagreewellwiththeexperimentaldata. withtwoNVIDIARTXA6000GPUs.
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-13
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

| Physics | of Fluids |     |     |     |     | ARTICLE |     | pubs.aip.org/aip/pof |     |
| ------- | --------- | --- | --- | --- | --- | ------- | --- | -------------------- | --- |
 12 September 2026 13:02:35
FIG.11.Absolutedifferenceof(a)velocityand(b)turbulentkineticenergybetweenthesimulationsfromPINNmodelandSSTk–xnumericalsolversat2.5D,5.5D,and8D
downstreamtheSexbierumHOLECWPS30/3windturbine.
Atotalof48000domainsamplingpointswereusedtotrainthe thereareopportunitiestoleverageatransferlearningapproach,where
3Dwakebehindthewindturbine.Thetrainingtook3307.62minto thetrainedmodelforonetypeofwindturbinecanbeusedasthestart-
complete.TheinferencewiththePINNmodelismuchfasteranddoes ingpointforanotherwindturbinesothattrainingcanbecompleted
not require the use of high-end GPUs. In our desktop setup with withlesscomputationasshownnext.
| NVIDIA | GeForce RTX | 2070, only milliseconds |     | were required to |     |     |     |     |     |
| ------ | ----------- | ----------------------- | --- | ---------------- | --- | --- | --- | --- | --- |
obtainthesimulationforthelineplotswith1000spatialpoints.The
A.Transferlearningtoreducetrainingtime
| inference | time for the | simulation to plot | the contours | was less than |     |     |     |     |     |
| --------- | ------------ | ------------------ | ------------ | ------------- | --- | --- | --- | --- | --- |
AsthetrainingtimeofthePINNmodelishigherthantherun-
| 10s using | a 500(cid:3)200(cid:3)1 | grid. Whenthe | model | is trained on two |         |                    |           |                    |              |
| --------- | ----------------------- | ------------- | ----- | ----------------- | ------- | ------------------ | --------- | ------------------ | ------------ |
|           |                         |               |       |                   | time of | a state-of-the-art | numerical | solver, we explore | the transfer |
GPUsvsoneGPU,wefoundthatthespeed-upratiowasonly1.4indi-
learningstrategytoreducecomputationaltrainingtimefornewturbu-
catingthatalinearscalingdoesnotoccurforthepresentPINNmodel
training.OnedrawbackofallthecurrentPINNframeworks(including lentflowsituationsfortheflowbehindasinglewindturbine.Intrans-
our model) is that the training time is high compared to a well- fer learning, a pre-trained model checkpoint is used as the starting
implemented CFD solver; however, with new advances in boundary point for training models for new tasks/situations. For the 3D wake
and initial condition generalization, we hope that the future will see behindasinglewindturbinetestcase,foraparticularturbine,chang-
modelsthataretrainedonceandusedforinferenceinout-of-distribu- ingthereferencevelocity(U )orturbulenceintensity(TI )changes
|     |     |     |     |     |     |     | ref |     | ref |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
tionsettings.AnotherimportantconsiderationisthatourPINNmod- theboundaryconditions,thrustandpoweroutput,therebyrequiring
newtrainingofthePINNmodel.Weemploytransferlearningtoshow
elsaretrainedonlyagainstthePDEresiduallossinsidethedomain.In
contrast, data-driven neural operators such as FNO or DeepONets howtoreducethistrainingtime.
requiresimulationdatafromaclassicalk(cid:1)eRANSCFDsolver.Thus,
|     |     |     |     |     | The | experimental | setup is | as follows: First, a PINN | model is |
| --- | --- | --- | --- | --- | --- | ------------ | -------- | ------------------------- | -------- |
¼10m=s
asignificantamountoftimewouldbeneededtogeneratethetraining trained with U ref for 25000 epochs and the converged
data itself, which our PINN training avoids. With neural networks, network’ssimulationistakenasareferencetoevaluatethequality
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-14
PublishedunderanexclusivelicensebyAIPPublishing

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
FIG.12.Absolutedifferenceof(a)velocityand(b)turbulenceintensitybetweenthesimulationsfromPINNmodelandSSTk–xnumericalsolverat2.5D,4D,and7.5Ddown-
streamtheNibe-Bwindturbine.
of the simulation produced by transfer learning. Another PINN fine-tuningareperformedinthistransferlearningtask.Thefine-
modelwithU ¼8m=sistrainedfromscratchfor25000epochs tuningtook682.32mincomparedtothe3307.62minutesfortrain-
ref
andisusedasthepre-trainedmodelfromwhichtransferlearning ing from scratch. Figure 13 shows the streamwise velocity and
isappliedtosimulatetheflowwithU ¼10m=s.5000epochsof pressurealongthecenterlineathubheightforthemodelcompared
ref
FIG.13.(a)Streamwisevelocityand(b)pressurealongthecenterlineathubheightfortheSexbierumHOLECWPS30/3windturbinefor(i)referencemodel(U ref¼10m=s),
(ii)pre-trainedmodel(U ref¼8m=s),and(iii)transferlearning(U ref¼10m=s).
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-15
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

| Physics | of Fluids |     |     |     |     |     |     |     | ARTICLE |     |     | pubs.aip.org/aip/pof |     |     |
| ------- | --------- | --- | --- | --- | --- | --- | --- | --- | ------- | --- | --- | -------------------- | --- | --- |
AUTHORDECLARATIONS
ConflictofInterest
Theauthorshavenoconflictstodisclose.
AuthorContributions
|     |     |     |     |     |     |     |     | Azhar Gafoor |     | CTP:   |          |         |               |         |
| --- | --- | --- | --- | --- | --- | --- | --- | ------------ | --- | ------ | -------- | ------- | ------------- | ------- |
|     |     |     |     |     |     |     |     |              |     | Formal | analysis | (lead); | Investigation | (lead); |
Methodology(equal);Software(equal);Visualization(lead);Writing–
originaldraft(equal).SumanthKumarBoya:Investigation(support-
|     |     |     |     |     |     |     |     | ing); Software | (supporting). |          | Rishi  | Jinka: Investigation |     | (supporting); |
| --- | --- | --- | --- | --- | --- | --- | --- | -------------- | ------------- | -------- | ------ | -------------------- | --- | ------------- |
|     |     |     |     |     |     |     |     | Software       | (supporting). | Abhineet | Gupta: | Conceptualization    |     | (equal);      |
FIG. 14.Schematic of the domain for turbulent channel flow together with the Methodology (supporting); Validation (equal). Ankit Tyagi:
boundaryconditions. Conceptualization (supporting); Methodology (supporting);
|     |     |     |     |     |     |     |     | Validation | (supporting). | Suranjan |     | Sarkar: Conceptualization |     | (sup- |
| --- | --- | --- | --- | --- | --- | --- | --- | ---------- | ------------- | -------- | --- | ------------------------- | --- | ----- |
porting);Methodology(supporting);Validation(supporting).Deepak
|     |     |     |     |     |     |     |     | Narayanan | Subramani: | Conceptualization |     | (equal); | Formal | analysis |
| --- | --- | --- | --- | --- | --- | --- | --- | --------- | ---------- | ----------------- | --- | -------- | ------ | -------- |
tothereferenceandthepre-trainedmodels.WeseethatthePINN
|     |     |     |     |     |     |     |     | (equal); | Funding | acquisition |     | (lead); | Investigation | (equal); |
| --- | --- | --- | --- | --- | --- | --- | --- | -------- | ------- | ----------- | --- | ------- | ------------- | -------- |
modelwithtransferlearningconvergedinonefifththenumberof
Methodology(equal);Software(equal);Supervision(lead);Validation
| epochs as | the model | trained | from | scratch. | Transfer | learning | to  |     |     |     |     |     |     |     |
| --------- | --------- | ------- | ---- | -------- | -------- | -------- | --- | --- | --- | --- | --- | --- | --- | --- |
(equal);Visualization(equal);Writing–originaldraft(equal).
| speed up | training | combined | with | the utility | of  | PINN | models to |     |     |     |     |     |     |     |
| -------- | -------- | -------- | ---- | ----------- | --- | ---- | --------- | --- | --- | --- | --- | --- | --- | --- |
performfastinferencemakesthemaviableoptioninwindenergy
simulators.
DATAAVAILABILITY
V. CONCLUSION The data and codes that support the findings of this study are
|       |                  |     |        |         |     |               |     | openly | available | in Github | at  | https://github.com/quest-lab-iisc/ |     |     |
| ----- | ---------------- | --- | ------ | ------- | --- | ------------- | --- | ------ | --------- | --------- | --- | ---------------------------------- | --- | --- |
| A new | physics-informed |     | neural | network |     | was developed | to  |        |           |           |     |                                    |     |     |
simulate turbulent wake using the RANS formulation with the 2- PINN_WakeTurbulenceModel and Zenodo https://doi.org/10.5281/
equation k(cid:1)e turbulence closure model. Wall functions and zenodo.13961398,Ref.76.  12 September 2026 13:02:35
sourcetermsforactuatordiskmodelswerealsoimplementedand
used.ThenewPINNmodelwastrainedusingonlyPDEresiduals APPENDIXA:2DFLOWCASES
| and boundary | conditions |          | without | using | data | from field    | experi- |                                          |     |     |     |     |     |     |
| ------------ | ---------- | -------- | ------- | ----- | ---- | ------------- | ------- | ---------------------------------------- | --- | --- | --- | --- | --- | --- |
| ments or     | numerical  | solvers. | Hence,  | the   | time | and expertise | the     |                                          |     |     |     |     |     |     |
|              |            |          |         |       |      |               |         | 1. Turbulentchannelflow(pressure-driven) |     |     |     |     |     |     |
data-drivenMLmodelsrequiretosetupandgenerate/pre-process
datafromnumericalsolversfortrainingareavoidedinthedevel- The2Dturbulentchannelflowisabenchmarktestcaseusedto
oped PINN model. The simulations showed excellent consistency validatenewapproachesforsolvingturbulentflowproblems.TheDNS
|          |            |     |      |            |      |         |        | solutions | available | for different | Reynolds | numbers | provide | excellent |
| -------- | ---------- | --- | ---- | ---------- | ---- | ------- | ------ | --------- | --------- | ------------- | -------- | ------- | ------- | --------- |
| with the | references | for | both | standalone | wind | turbine | cases. |           |           |               |          |         |         |           |
dataforvalidatingourPINNmodelandforhyperparametertuning.
AlthoughthetrainingtimeforthePINNmodelsishighcompared
TheflowgeometryforthistestcaseissetasshowninFig.14
tothewell-implementedparallelnumericalsolvers,therearequite
(followingRef.78).Theflowbetweentwoflatplatesseparatedbya
| a few advantages |     | in considering |     | PINNs | as a promising |     | approach |     |     |     |     |     |     |     |
| ---------------- | --- | -------------- | --- | ----- | -------------- | --- | -------- | --- | --- | --- | --- | --- | --- | --- |
distanceof2hinthefullydevelopedregimeisdrivenbyaconstant
forsolvingPDEs.ThePINNmodelprovidesamesh-freesolution
by forming a complex function map between input and output. negativepressuregradientinthestreamwisedirection,whichisbal-
Hence, during the swift inference, the PINN model can give the ancedbythewallshearstress.Thefullydevelopedturbulentchan-
solutionatanypointinthedomainoutofthebox.Inaddition,by nel flowis symmetricwithrespect tothecenterline.Therefore,the
|     |     |     |     |     |     |     |     | simulation | is performed | only | in  | a domain | restricted | to half the |
| --- | --- | --- | --- | --- | --- | --- | --- | ---------- | ------------ | ---- | --- | -------- | ---------- | ----------- |
usingautomaticdifferentiation,thecomplexdiscretizationprocess
|                 |           |     |         |             |         |     |             | channel | height. | The flow | is also homogeneous |     | in the | streamwise |
| --------------- | --------- | --- | ------- | ----------- | ------- | --- | ----------- | ------- | ------- | -------- | ------------------- | --- | ------ | ---------- |
| in conventional | numerical |     | solvers | is avoided. | Further |     | theoretical |         |         |          |                     |     |        |            |
andspanwisedirections.Thus,inthiswork,thesimulationisdone
andimplementationoptimization,suchasboundaryandgeometry
|     |     |     |     |     |     |     |     | in 2D. In | addition, | the ability | of  | the PINN | model | to develop a |
| --- | --- | --- | --- | --- | --- | --- | --- | --------- | --------- | ----------- | --- | -------- | ----- | ------------ |
parameterizationcombinedwithtransferlearningtechniques,can
homogeneousflowisusedasavalidationcriterion.
enablethetrainedmodeltoinfernewflowcaseswithouttheneed
TheflowissimulatedforfrictionReynoldsnumbers(Res)180,
totrainfromscratch.
395,and590.Resisdefinedas
| ACKNOWLEDGMENTS |     |     |     |     |     |     |     |     |     |     |       | u sh |     |      |
| --------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ----- | ---- | --- | ---- |
|                 |     |     |     |     |     |     |     |     |     |     | Res ¼ | ;    |     | (A1) |
(cid:2)
| We thank | all | members | of the | QUEST | Lab | at IISc | for useful |     |     |     |     |     |     |     |
| -------- | --- | ------- | ------ | ----- | --- | ------- | ---------- | --- | --- | --- | --- | --- | --- | --- |
discussions. The authors are grateful for the Prime Minister’s whereusisthefrictionvelocity,hishalfchannelwidth,and(cid:2)isthe
Research Fellowship (PMRF) from the Ministry of Education to kinematic viscosity. The constant pressure gradient, which drives
AzharGafoorCTP.
theflowinthestreamwisedirection,mustbeprovided.Bysimplify-
Thisresearchwaspartiallysupportedbyresearchgrantsfrom ing the momentum equation in the streamwise direction (x), the
theMinistryofEarthSciences(MoES/36/OOIS/Extra/84/2022)and pressure gradient can be expressed in terms of density, channel
| ShellIndiaMarketsPrivateLimited. |     |     |     |     |     |     |     | widthandfrictionvelocityas |     |     |     |     |     |     |
| -------------------------------- | --- | --- | --- | --- | --- | --- | --- | -------------------------- | --- | --- | --- | --- | --- | --- |
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-16
PublishedunderanexclusivelicensebyAIPPublishing

| Physics | of Fluids |     |     | ARTICLE | pubs.aip.org/aip/pof |        |           |
| ------- | --------- | --- | --- | ------- | -------------------- | ------ | --------- |
|         |           |     |     |         | FIG. 15.Comparison   | of the | turbulent |
channelflowprofilesof(a)meanvelocity,
(b)turbulentkineticenergy,(c)rateofdis-
|     |     |     |     |     | sipation of      | TKE, and (d) turbulent | shear      |
| --- | --- | --- | --- | --- | ---------------- | ---------------------- | ---------- |
|     |     |     |     |     | stress simulated | from the               | PINN model |
|     |     |     |     |     | with DNS         | data and RANS solution | from       |
CFDsolverforfrictionReynoldsnumbers  12 September 2026 13:02:35
of180,395,and590.
@ q
p : s p e ci fi e d on the bottom wall using the wall function equations as
|     | ¼(cid:1) | u2  | (A2)          |     |     |     |     |
| --- | -------- | --- | ------------- | --- | --- | --- | --- |
|     | @ x h    | s   | fo l lo w s : |     |     |     |     |
The inlet and outlet boundaries are given periodic boundary 2 u3
|     |     |     |     | us lnyþþB; | k¼p u ffi sffiffiffiffiffi; | e¼ s: |     |
| --- | --- | --- | --- | ---------- | --------------------------- | ----- | --- |
u¼
conditions to satisfy homogeneity in the streamwise direction. At j Cl jy
| the top boundary, | symmetry conditions | are applied | by specifying |     |     |     |     |
| ----------------- | ------------------- | ----------- | ------------- | --- | --- | --- | --- |
zeroforthevelocityinthewall-normaldirectionandthegradients Weusedahalfchannelheightof1mandastreamwiselength
of other quantities with respect to the wall-normal direction. The of10m.Asweusewallfunctions,thebottomboundaryisnotgiven
velocity, turbulent kinetic energy, and dissipation rate values are at y¼0m but at a specified height yþ¼60 so that the boundary
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-17
PublishedunderanexclusivelicensebyAIPPublishing

| Physics | of Fluids |     |     |     |     |     | ARTICLE |     | pubs.aip.org/aip/pof |     |     |     |
| ------- | --------- | --- | --- | --- | --- | --- | ------- | --- | -------------------- | --- | --- | --- |
model.ProfilesoftheDNSandRANSCFDsimulationsofthefully
developedflowarealsoshownforreference.Itcanbeseenthatthe
|     |     |     |     |     |     | simulated | profiles | match well | with the  | data.     | Since we    | employ wall |
| --- | --- | --- | --- | --- | --- | --------- | -------- | ---------- | --------- | --------- | ----------- | ----------- |
|     |     |     |     |     |     | functions | to model | near-wall  | behavior, | the       | simulated   | profiles    |
|     |     |     |     |     |     | obtained  | from our | PINN model | begin     | only from | the overlap | layer       |
oftheturbulentboundarylayer,asisthecasewiththeRANSCFD
|     |     |     |     |     |     | simulation.                                      | From | the figure, | it can | also be | seen that | our PINN  |
| --- | --- | --- | --- | --- | --- | ------------------------------------------------ | ---- | ----------- | ------ | ------- | --------- | --------- |
|     |     |     |     |     |     | model wellpredictsthefullydevelopedorhomogeneous |      |             |        |         |           | condition |
inthestreamwisedirection.
|                      |        |                       |               |           |           | 2. Velocity-drivenstreamwisehomogeneousflow |     |     |     |     |     |     |
| -------------------- | ------ | --------------------- | ------------- | --------- | --------- | ------------------------------------------- | --- | --- | --- | --- | --- | --- |
| FIG. 16.Illustration | of the | vertical distribution | of horizontal | velocity, | TKE/shear |                                             |     |     |     |     |     |     |
Asthesecondtestcase,wechoosethevelocity-drivenstream-
| stress and | dissipation rate for | the velocity-driven | streamwise | homogeneous | flow. |                  |     |           |          |                   |     |              |
| ---------- | -------------------- | ------------------- | ---------- | ----------- | ----- | ---------------- | --- | --------- | -------- | ----------------- | --- | ------------ |
|            |                      |                     |            |             |       | wise homogeneous |     | flow with | specific | inlet conditions. |     | This flow is |
Themagnitudeofquantitiesincreasesfromlefttoright.
anaddedcomplexitytotheturbulentchannelflowtestcase,where
|     |     |     |     |     |     | the inlet | is an atmospheric |     | flow profile79 | commonly |     | used in the |
| --- | --- | --- | --- | --- | --- | --------- | ----------------- | --- | -------------- | -------- | --- | ----------- |
fallsinthelog-lawregion(30<yþ<500)oftheturbulentbound-
|     |     |     |     |     |     | atmospheric | boundary | layer | (ABL) | flow simulations. |     | We use the |
| --- | --- | --- | --- | --- | --- | ----------- | -------- | ----- | ----- | ----------------- | --- | ---------- |
ary layer. By setting friction velocity (us) equal to 1m/s, the kine- standardk(cid:1)emodelwiththewallfunctionsmodifiedtobeconsis-
maticviscosity((cid:2))canbesetto1/180,1/395,and1/590m2/susing
tentwiththeinletprofiles.Figure16showstheinletflow,turbulent
| Eq. (A1) | to achieve friction | Reynolds | numbers | 180, 395 | and 590. |     |     |     |     |     |     |     |
| -------- | ------------------- | -------- | ------- | -------- | -------- | --- | --- | --- | --- | --- | --- | --- |
kineticenergy,anddissipationrateprofilesinthedomain.
Sincethechannelflowisfullydeveloped,theconstantpressuregra-
| dient is | set equal to | (cid:1)1Pa/m | using Eq. | (A2) for | density |     |     |     |     |     |     |     |
| -------- | ------------ | ------------ | --------- | -------- | ------- | --- | --- | --- | --- | --- | --- | --- |
q¼1kg=m3.
a.PINNmodelsimulations
 12 September 2026 13:02:35
Figure15showstheverticaldistributionofmeanvelocity,tur-
bulentkineticenergy,dissipationrate,andturbulentshearstressat
| the midpoint | and outlet | of the | channel obtained | from our | PINN |     |     |     |     |     |     |     |
| ------------ | ---------- | ------ | ---------------- | -------- | ---- | --- | --- | --- | --- | --- | --- | --- |
FIG.18.Comparisonofturbulentchannelflowprofilesof(a)meanvelocity,(b)tur-
bulentkineticenergy,(c)rateofdissipationofTKE,and(d)turbulentshearstress
FIG.17.(a)Streamwisevelocity,(b)turbulentkineticenergy,and(c)turbulentdissi- simulatedfromthePINNmodels,fordifferentweightsinEq.(3),withDNSdataand
pationrateprofilesoftheABLflowsimulatedfromPINNmodelsarecomparedto RANSsolutionfromCFDsolverforfrictionReynoldsnumbersof180.Table(e)lists
| thereference(inletprofile). |     |     |     |     |     | theweightsusedinPINNmodels. |     |     |     |     |     |     |
| --------------------------- | --- | --- | --- | --- | --- | --------------------------- | --- | --- | --- | --- | --- | --- |
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-18
PublishedunderanexclusivelicensebyAIPPublishing

| Physics | of Fluids |     |     |     | ARTICLE | pubs.aip.org/aip/pof |     |
| ------- | --------- | --- | --- | --- | ------- | -------------------- | --- |
 12 September 2026 13:02:35
FIG.19.(a)Velocityand(b)turbulentkineticenergysimulationsusingSSTk–xturbulencemodelinSTARCCMþnumericalsolverfordifferentgridresolutionsat2.5D,5.5D,
and8DdownstreamtheSexbierumwindturbine.Alowermeshbasesizedenotesafinergrid.
Anothermotivationtochoosethistestcaseisasfollows.With Atthebottomwall/ground,z¼z isusedinEq.(8)forspecify-
p
the influence of boundaries and no external forcing, the model ing conditions. Here, z p is the height from the ground such that
90<zpus<500.69Atthetopboundary,symmetryboundarycondi-
| shouldbeabletosimulatetheflow,maintaininghomogeneityinthe |     |     |     | (cid:2) |     |     |     |
| --------------------------------------------------------- | --- | --- | --- | ------- | --- | --- | --- |
streamwise direction for the given inlet conditions. Even with an tionsareusedforvelocity,pressure,andotherturbulentquantities.
obstacle(e.g.,buildingorwindturbines)inthedomain,sufficiently Apressureoutletboundaryconditionisspecifiedfortheoutletwith
homogeneous profiles are required upstream and downstream of nostreamwisegradientsofotherquantities.
| the obstacle | for minimizing   | the ground/boundary | effects.69     | Thus, |     |     |     |
| ------------ | ---------------- | ------------------- | -------------- | ----- | --- | --- | --- |
| this test    | case establishes | the ability of      | our PINN model | to    |     |     |     |
b.PINNmodelsimulations
simulatehomogeneousflow.Specifically,thesuccesscriteriaforour
model’s Figure17showsthestreamwisevelocity,turbulentkineticenergy,
| PINN     | ability to simulate      | horizontally | homogeneous | flow            |                        |               |               |
| -------- | ------------------------ | ------------ | ----------- | --------------- | ---------------------- | ------------- | ------------- |
|          |                          |              |             | and dissipation | rate profiles obtained | from the PINN | model plotted |
| are that | the simulated downstream | velocity,    | turbulent   | kinetic         |                        |               |               |
energy, and dissipation profiles must match the provided inlet againstheight.Thereferenceinletprofileisalsoshownforcomparison.
8m=s
profile. Here,we useareferencevelocity(u ref )of atareferenceheight
(z )of70mandaturbulenceintensityof7%.Thedomainhasaheight
ref
of100mandastreamwiselengthof200m.Thefrictionvelocity,calcu-
|                      |     |     |     | latedusingEq.(8a)withz | ¼0:001m,isusedtoobtainthevaluesof |     |     |
| -------------------- | --- | --- | --- | ---------------------- | --------------------------------- | --- | --- |
| a.Boundaryconditions |     |     |     |                        | 0                                 |     |     |
otherturbulentquantities.Asuccessfulsimulationwouldhaveobtained
Forvelocity-drivenstreamwisehomogeneousflow,fullydevel- horizontallyhomogeneousflow;thatis,thePINNsimulationsandref-
oped inlet profiles for mean velocity [Eq. (8a)], turbulent kinetic erenceinletprofileswouldbeidentical.Theflowisalsocharacterized
energy[Eq.(8b)]andturbulentdissipationrate[Eq.(8c)]arespeci- byconstant shearstress, providingavertical lineas the profile of the
fiedattheinletboundary.79 turbulentkineticenergy(Fig.17panelforTKE).
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-19
PublishedunderanexclusivelicensebyAIPPublishing

| Physics | of Fluids |     |     |     |     |     |     |     | ARTICLE |     |     | pubs.aip.org/aip/pof |     |     |     |
| ------- | --------- | --- | --- | --- | --- | --- | --- | --- | ------- | --- | --- | -------------------- | --- | --- | --- |
InFig.17,itcanbeseenthatthevelocity,TKE,anddissipation windfarmformeshbasesizefrom0.4Dto0.025D.Thedifference
rate profiles simulated by the PINN model are in good agreement of the calculated velocities and turbulence quantities from simula-
withtheinletreferenceprofile.Althoughthedeviationseemstobe tionsforbasesizes0.025Dand0.05Disminimal.Hence,themesh
thehighestfortheTKEprofile,themeanabsoluteerroristheleast basesizeof0.05Dguaranteesamesh-independentsolution.
| for this | variable. | The | mean | absolute | errors | for | velocity is |     |     |     |     |     |     |     |     |
| -------- | --------- | --- | ---- | -------- | ------ | --- | ----------- | --- | --- | --- | --- | --- | --- | --- | --- |
0:73667(cid:3)10(cid:1)1,forTKEis0:00567(cid:3)10(cid:1)3,andfordissipation
REFERENCES
rateis0:04766(cid:3)10(cid:1)1.
1P.
|     |     |     |     |     |     |     |     | Pandiyan, | R.  | Sitharthan, | S. Saravanan, |     | N. Prabaharan, | M. R. Tiwari, | T.  |
| --- | --- | --- | --- | --- | --- | --- | --- | --------- | --- | ----------- | ------------- | --- | -------------- | ------------- | --- |
Chinnadurai,T.Yuvaraj,andK.R.Devabalaji,“Acomprehensivereviewofthe
prospectsforruralelectrificationusingstand-aloneandhybridenergytechnol-
APPENDIXB:WEIGHTSFORRESIDUALAND
ogies,”SustainableEnergyTechnol.Assess.52,102155(2022).
BOUNDARYLOSSES
|     |     |     |     |     |     |     |     | 2A. L(cid:2)opez-Gonz(cid:2)alez, |     | M.  | Ranaboldo, | B. Domenech, |     | and L. Ferrer-Martí, |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --------------------------------- | --- | --- | ---------- | ------------ | --- | -------------------- | --- |
“Evaluation
|     |     |     |     |     |     |     |     |     | of  | small wind | turbines | for rural | electrification: | Case | studies |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---------- | -------- | --------- | ---------------- | ---- | ------- |
Inconventionalnumericalmethods,ineachiteration,theflow Venezuela,”
|            |             |     |                 |     |               |      |        | from extreme |     | climatic | conditions | in  |     | Energy 209, | 118450 |
| ---------- | ----------- | --- | --------------- | --- | ------------- | ---- | ------ | ------------ | --- | -------- | ---------- | --- | --- | ----------- | ------ |
| parameters | are updated |     | in a sequential |     | way. Starting | from | one of | (2020).      |     |          |            |     |     |             |        |
the discretized equations and then approaching the subsequent 3J. Li, P. Liu, and Z. Li, “Optimal design and techno-economic analysis of a
equations.Hence,iteratively,theconvergenceisattainedbyconsid- solar-wind-biomassoff-gridhybridpowersystemforremoteruralelectrifica-
ering the effects of all the equations. Meanwhile, in the training tion:AcasestudyofwestChina,”Energy208,118387(2020).
4P.MoinandK.Mahesh,“Directnumericalsimulation:Atoolinturbulence
| phase of | the PINN | model, | the | information | from | all PDEs | is cap- |     |     |     |     |     |     |     |     |
| -------- | -------- | ------ | --- | ----------- | ---- | -------- | ------- | --- | --- | --- | --- | --- | --- | --- | --- |
research,”Annu.Rev.FluidMech.30,539–578(1998).
| tured simultaneously. |     | Thus, | the | dominant | PDE | will influence | the |     |     |     |     |     |     |     |     |
| --------------------- | --- | ----- | --- | -------- | --- | -------------- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
5P.J.Mason,“Large-eddysimulation:Acriticalreviewofthetechnique,”Q.J.
parameter learning of the neural network, ignoring the effect of R.Meteorol.Soc.120,1–26(1994).
otherequationsinthedomain.Toavoidthis,aweightingstrategyis 6C. G. Speziale, “Analytical methods for the development of Reynolds-Stress
closuresinturbulence,”Annu.Rev.FluidMech.23,107–157(1991).
| adoptedto | giveequivalent |     | importance |     | toalltheequations |     | and the |     |     |     |     |     |     |     |     |
| --------- | -------------- | --- | ---------- | --- | ----------------- | --- | ------- | --- | --- | --- | --- | --- | --- | --- | --- |
7J.P.Slotnick,A.Khodadoust,J.Alonso,D.Darmofal,W.Gropp,E.Lurie,and
boundarylosseswhiletraining.Theturbulentchannelflowforfric-
D.J.Mavriplis,“CFDvision2030study:Apathtorevolutionarycomputational
| tion Reynolds                                         | numbers |     | of 180 is | simulated | using | the PINN | model |                                                       |           |        |     |                     |     |        |        |
| ----------------------------------------------------- | ------- | --- | --------- | --------- | ----- | -------- | ----- | ----------------------------------------------------- | --------- | ------ | --- | ------------------- | --- | ------ | ------ |
|                                                       |         |     |           |           |       |          |       | aerosciences,”                                        | Technical | Report | No. | NASA/CR-2014-218178 |     | (NASA, | Boeing |
| forweightsmentionedinEq.(3)inagridsearchmethodology.a |         |     |           |           |       |          | is    |                                                       |           |        |     |                     |     |        |        |
|                                                       |         |     |           |           |       |          | b     | Research&Technology,HuntingtonBeach,California,2014). |           |        |     |                     |     |        |        |
the weighting coefficient for boundary losses, a is the weighting 8C.P(cid:2)erez,O.Lehmkuhl, G.Colomer,andA.Oliva,“Turbulence
|     |     |     |     |     |     | r   |     |     |     | J.Jaramillo, |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ------------ | --- | --- | --- | --- | --- |
coefficientforresiduallosses,anda aretheweightingcoefficients LES,”  12 September 2026 13:02:35
1(cid:1)4 modelling and numerical issues: From RANS to DNS and in III
assigned to the residuals of the governing PDEs: continuity equa- Confer^encia Mec^anica Termodin^amica
|                |     |           |           |     |           |           |     |                 | Nacional | em  |     | de Fluidos, |     | e   | Energia, |
| -------------- | --- | --------- | --------- | --- | --------- | --------- | --- | --------------- | -------- | --- | --- | ----------- | --- | --- | -------- |
| tion, momentum |     | transport | equation, | TKE | transport | equation, | and | Braganc¸a,2009. |          |     |     |             |     |     |          |
9M.Breuer,N.Jovi(cid:3)ci(cid:2)c,andK.Mazaev,“ComparisonofDES,RANSandLESfor
| TKE dissipation |     | transport | equation, | respectively. |     | Figure | 18 shows |               |      |        |        |          |                  |         |        |
| --------------- | --- | --------- | --------- | ------------- | --- | ------ | -------- | ------------- | ---- | ------ | ------ | -------- | ---------------- | ------- | ------ |
|                 |     |           |           |               |     |        |          | the separated | flow | around | a flat | plate at | high incidence,” | Int. J. | Numer. |
thecomparison ofprofiles oftheturbulent channelflowsimulated MethodsFluids41,357–388(2003).
from the PINN models with DNS data and RANS solution from 10P.M.Doran,“Chapter7—Fluidflow,”inBioprocessEngineeringPrinciples,2nd
CFDsolver.Thetableinthefigureliststheweightsusedfordiffer- ed.(AcademicPress,London,2013),pp.201–254.
(a
ent PINN models. When the weight for the boundary loss ) is 11M.Raissi,P.Perdikaris,andG.E.Karniadakis,“Physics-informedneuralnet-
b
givenas1,themodelcannotcapturetheslopeofthevelocityprofile works: A deep learning framework for solving forward and inverse problems
resulting in poor prediction of the turbulent shear stress. On involvingnonlinearpartialdifferentialequations,”J.Comput.Phys.378,686–
| increasingthesameto10,theprofilesagreewiththeRANSsimula- |     |     |     |     |     |     |     | 707(2019). |     |     |     |     |     |     |     |
| -------------------------------------------------------- | --- | --- | --- | --- | --- | --- | --- | ---------- | --- | --- | --- | --- | --- | --- | --- |
12A.G.Baydin,B.A.Pearlmutter,A.A.Radul,andJ.M.Siskind,“Automaticdiffer-
| tions, and | on further |     | increase, | the profiles | start | to deviate. | The |                 |           |                  |             |               |                      |                      |         |
| ---------- | ---------- | --- | --------- | ------------ | ----- | ----------- | --- | --------------- | --------- | ---------------- | ----------- | ------------- | -------------------- | -------------------- | ------- |
|            |            |     |           |              |       |             |     | e n t ia ti o n | in m a ch | in e le a rn i n | g: A s u rv | e y ,” J. M a | c h. L e a r n . R e | s. 1 8 , 1 –4 3 (2 0 | 1 8 ) . |
weightsof“PINN7”arechosenforthePINNmodelasthesimula-
|     |     |     |     |     |     |     |     | 13 L . L u , P | . Jin , G . | P an g , Z . | Z h an g , a | n d G . E | . K ar n i a d a k is | , “ L e a rn in g n | o n l i near |
| --- | --- | --- | --- | --- | --- | --- | --- | -------------- | ----------- | ------------ | ------------ | --------- | --------------------- | ------------------- | ------------ |
tionfromthemodelagreeswiththenumericalresults.
|     |     |     |     |     |     |     |     | operators | via DeepONet |     | based on | the universal | approximation | theorem | of  |
| --- | --- | --- | --- | --- | --- | --- | --- | --------- | ------------ | --- | -------- | ------------- | ------------- | ------- | --- |
operators,”Nat.Mach.Intell.3,218–229(2021).
14Z.Li,N.Kovachki,K.Azizzadenesheli,B.Liu,K.Bhattacharya,A.Stuart,and
APPENDIXC:CFD:MESHCONVERGENCEANALYSIS A. Anandkumar, “Fourier neural operator for parametric partial differential
equations,”arXiv:2010.08895(2020).
Ameshconvergenceanalysisisdonetoreducespatialdiscreti- 15F.Bartolucci,E.deBezenac,B.Raonic,R.Molinaro,S.Mishra,andR.Alaifari,
zation errors in the CFD simulations and to guarantee a mesh- “Representationequivalentneuraloperators:Aframeworkforalias-freeopera-
learning,”
independentsolution.Thesimulationsarebasedonthesinglewind tor Advances in Neural Information Processing Systems (Curran
turbine of the Sexbierum wind farm. The size of both the back- AssociatesInc.,RedHook,NY,USA,2024),Vol.36.
16A.P.Singh,S.Medida,andK.Duraisamy,“Machine-learning-augmentedpre-
| ground mesh | and | the refined | disk | mesh | is varied | as a | function of |     |     |     |     |     |     |     |     |
| ----------- | --- | ----------- | ---- | ---- | --------- | ---- | ----------- | --- | --- | --- | --- | --- | --- | --- | --- |
dictivemodelingofturbulentseparatedflowsoverairfoils,”AIAAJ.55,2215–
| the turbine | diameter | for | a single | turbine | by defining | a   | mesh base |     |     |     |     |     |     |     |     |
| ----------- | -------- | --- | -------- | ------- | ----------- | --- | --------- | --- | --- | --- | --- | --- | --- | --- | --- |
2227(2017).
size.Theideabehindthebasesizeistosetothervalueslikesurface 17K.Duraisamy,G.Iaccarino,andH.Xiao,“Turbulencemodelingintheageof
targetsizeandboundarylayerthickness,e.g.,proportionallytothe data,”Annu.Rev.FluidMech.51,357–377(2019).
base value. The mesh canbe refined or coarsened bychanging the 18Z.Zhou,G.He,S.Wang,andG.Jin,“Subgrid-scalemodelforlarge-eddysimu-
basesizevalue.Allothervaluesdefinedbytheratiotothebasesize lationofisotropicturbulentflowsusinganartificialneuralnetwork,”Comput.
Fluids195,104319(2019).
| will change | automatically. |     | In  | the simulations, |     | the base | size is |              |         |             |     |            |          |           |          |
| ----------- | -------------- | --- | --- | ---------------- | --- | -------- | ------- | ------------ | ------- | ----------- | --- | ---------- | -------- | --------- | -------- |
|             |                |     |     |                  |     |          |         | 19R. Maulik, | O. San, | A. Rasheed, | and | P. Vedula, | “Subgrid | modelling | for two- |
decreased progressively by a factor of 2, starting from the coarsest dimensionalturbulenceusingneuralnetworks,”J.FluidMech.858,122–144(2019).
case of 0.4D. Figure 19 shows the velocity and turbulent kinetic 20N.Thuerey,K.Weißenow,L.Prantl,andX.Hu,“Deeplearningmethodsfor
energy simulations using STARCCMþ numerical solver at 2.5D, Reynolds-averagedNavier–Stokessimulationsofairfoilflows,”AIAAJ.58,25–
| 5.5D,and8DdownstreamthesinglewindturbineoftheSexbierum |     |     |     |     |     |     |     | 36(2020). |     |     |     |     |     |     |     |
| ------------------------------------------------------ | --- | --- | --- | --- | --- | --- | --- | --------- | --- | --- | --- | --- | --- | --- | --- |
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-20
PublishedunderanexclusivelicensebyAIPPublishing

Physics of Fluids ARTICLE pubs.aip.org/aip/pof
21Y.Yin,P.Yang,Y.Zhang,H.Chen,andS.Fu,“Featureselectionandprocessing 47A.Takbiri-Borujeni,H.Kazemi,andN.Nasrabadi,“Adata-drivensurrogateto
ofturbulencemodelingbasedonanartificialneuralnetwork,”Phys.Fluids32, image-basedflowsimulationsinporousmedia,”Comput.Fluids201,104475
105117(2020). (2020).
22B.Tracey,K.Duraisamy,andJ.Alonso,“Applicationofsupervisedlearningto 48N.Kovachki,Z.Li,B.Liu,K.Azizzadenesheli,K.Bhattacharya,A.Stuart,and
quantifyuncertaintiesinturbulenceandcombustionmodeling,”in51stAIAA A. Anandkumar, “Neural operator: Learning maps between function spaces
Aerospace Sciences Meeting Including the New Horizons Forum and withapplicationstoPDEs,”J.Mach.Learn.Res.24,4061–4157(2023).
AerospaceExposition,AIAAPaperNo.AIAA2013-0259,2013. 49Z.Li,N.Kovachki,K.Azizzadenesheli,B.Liu,K.Bhattacharya,A.Stuart,and
23B.D.Tracey,K.Duraisamy,andJ.J.Alonso,“Amachinelearningstrategyto A.Anandkumar,“Neuraloperator:Graphkernelnetworkforpartialdifferen-
assist turbulence model development,” in 53rd AIAA Aerospace Sciences tialequations,”arXiv:2003.03485(2020).
Meeting,AIAAPaperNo.AIAA2015-1287,2015. 50B.Raonic, R.Molinaro,T.DeRyck,T.Rohner,F.Bartolucci,R.Alaifari,S.
24J.-X. Wang, J.-L. Wu, and H. Xiao, “Physics-informed machine learning Mishra, and E. de B(cid:2)ezenac, “Convolutional neural operators for robust and
approachforreconstructingReynoldsstressmodelingdiscrepanciesbasedon accuratelearningofPDEs,”AdvancesinNeuralInformationProcessingSystems
DNSdata,”Phys.Rev.Fluids2,034603(2017). (CurranAssociatesInc.,RedHook,NY,USA,2024),Vol.36.
25J.-L. Wu, H. Xiao, and E. Paterson, “Physics-informed machine learning 51M.Raissi,P.Perdikaris,andG.E.Karniadakis,“Physicsinformeddeeplearning
approach for augmenting turbulence models: A comprehensive framework,” (Part I): Data-driven solutions of nonlinear partial differential equations,”
Phys.Rev.Fluids3,074602(2018). arXiv:1711.10561(2017).
26M.L.A.KaandorpandR.P.Dwight,“Data-drivenmodellingoftheReynolds 52M.Kazemi,A.Takbiri-Borujeni,S.Takbiri,andA.Kazemi,“Physics-informed
stress tensor using random forests with invariance,” Comput. Fluids 202, data-driven model for fluid flow in porous media,” Comput. Fluids 264,
104497(2020). 105960(2023).
27J. Ling, A. Kurzawski, and J. A. Templeton, “Reynolds averaged turbulence 53H.Zhang,H.Wang,Z.Xu,Z.Liu,andB.C.Khoo,“Aphysics-informedneural
modelling using deep neural networks with embedded invariance,” J. Fluid network-based approach to reconstruct the tornado vortices from limited
Mech.807,155–166(2016). observeddata,”J.WindEng.Ind.Aerodyn.241,105534(2023).
28L.Zhu,W.Zhang,J.Kou,andY.Liu,“Machinelearningmethodsforturbu- 54J.-D.Mu€llerandP.Cusdin,“OntheperformanceofdiscreteadjointCFDcodes
lence modeling in subsonic flows around airfoils,” Phys. Fluids 31, 015105 using automatic differentiation,” Int. J. Numer. Methods Fluids 47, 939–945
(2019). (2005).
29X.Sun,W.Cao,Y.Liu,L.Zhu,andW.Zhang,“HighReynoldsnumberairfoil 55J.Thomas,E.Dowell,andK.Hall,“Usingautomaticdifferentiationtocreatea
turbulencemodelingmethodbasedonmachinelearningtechnique,”Comput. nonlinearreducedordermodelofacomputationalfluiddynamic solver,”in
Fluids236,105298(2022). 11th AIAA/ISSMO Multidisciplinary Analysis and Optimization Conference,
30M.MilanoandP.Koumoutsakos,“Neuralnetworkmodelingfornearwalltur- AIAAPaperNo.AIAA2006-7115,2006.
bulentflow,”J.Comput.Phys.182,1–26(2002). 56C.H.Bischof,H.M.Bu€cker,A.Rasch,E.Slusanschi,andB.Lang,“Automatic
31H.Xu,W.Zhang,andY.Wang,“Exploremissingflowdynamicsbyphysics- differentiation of the general-purpose computational fluid dynamics package
informed deep learning: The parameterized governing systems,” Phys. Fluids FLUENT,”J.FluidsEng.129,652–658(2007).
33,095116(2021). 57S.Luo,M.Vellakal,S.Koric,V.Kindratenko,andJ.Cui,“Parameteridentifica-
32J.Wu,H.Xiao,R.Sun,andQ.Wang,“Reynolds-averagedNavier–Stokesequa- tionofRANSturbulencemodelusingphysics-embeddedneuralnetwork,”in
tionswithexplicitdata-drivenReynoldsstressclosurecanbeill-conditioned,” InternationalConferenceonHighPerformanceComputing(Springer,2020),pp.
J.FluidMech.869,553–586(2019). 137–149.
33S.V.Poroseva,J.D.ColmenaresF,andS.M.Murman,“Ontheaccuracyof 58O.Hennigh,S.Narasimhan,M.A.Nabian,A.Subramaniam,K.Tangsali,Z.
RANSsimulationswithDNSdata,”Phys.Fluids28,115102(2016). Fang,M.Rietmann,W.Byeon,andS.Choudhry,“NVIDIASimNetTM:AnAI-
34R.L.Thompson,L.E.B.Sampaio,F.A.deBraganc¸aAlves,L.Thais,andG. acceleratedmulti-physicssimulationframework,”inInternationalConference
Mompean,“AmethodologytoevaluatestatisticalerrorsinDNSdataofplane onComputationalScience(Springer,2021),pp.447–461.
channelflows,”Comput.Fluids130,1–7(2016). 59H.Eivazi,M.Tahani,P.Schlatter,andR.Vinuesa,“Physics-informedneural
35R.Fang,D.Sondak,P.Protopapas,andS.Succi,“Deeplearningforturbulent networksforsolvingReynolds-averagedNavier–Stokesequations,”Phys.Fluids
channelflow,”arXiv:1812.02241(2018). 34,075117(2022).
36J. Bongard and H. Lipson, “Automated reverse engineering of nonlinear 60M.-J.Xiao,T.-C.Yu,Y.-S.Zhang,andH.Yong,“Physics-informedneuralnet-
dynamicalsystems,”Proc.Natl.Acad.Sci.U.S.A.104,9943–9948(2007). worksfortheReynolds-averagedNavier–StokesmodelingofRayleigh–Taylor
37M.SchmidtandH.Lipson,“Distillingfree-formnaturallawsfromexperimen- turbulentmixing,”Comput.Fluids266,106025(2023).
taldata,”Science324,81–85(2009). 61S.Ghosh,A.Chakraborty,G.O.Brikis,andB.Dey,“RANS-PINNbasedsimu-
38S.L.Brunton,J.L.Proctor,andJ.N.Kutz,“Discoveringgoverningequations lationsurrogatesforpredictingturbulentflows,”arXiv:2306.06034(2023).
fromdatabysparseidentificationofnonlineardynamicalsystems,”Proc.Natl. 62V.Kag,K.Seshasayanan,andV.Gopinath,“Physics-informeddatabasedneu-
Acad.Sci.U.S.A.113,3932–3937(2016). ralnetworksfortwo-dimensionalturbulence,”Phys.Fluids34,055130(2022).
39S.H.Rudy,S.L.Brunton,J.L.Proctor,andJ.N.Kutz,“Data-drivendiscovery 63L. Riccius, A. Agrawal, and P.-S. Koutsourelakis, “Physics-informed tensor
ofpartialdifferentialequations,”Sci.Adv.3,e1602614(2017). basis neural network for turbulence closure modeling,” arXiv:2311.14576
40H. Schaeffer, “Learning partial differential equations via data discovery and (2023).
sparseoptimization,”Proc.Math.Phys.Eng.Sci.473,20160446(2017). 64B.E.LaunderandB.I.Sharma,“Applicationoftheenergy-dissipationmodel
41M.RaissiandG.E.Karniadakis,“Hiddenphysicsmodels:Machinelearningof ofturbulencetothecalculationofflownearaspinningdisc,”Lett.HeatMass
nonlinearpartialdifferentialequations,”J.Comput.Phys.357,125–141(2018). Transfer1,131–137(1974).
42Z.Long,Y.Lu,X.Ma,andB.Dong,“PDE-Net:LearningPDEsfromdata,”in 65A. Crespo, F. Manuel, D. Moreno, E. Fraga, and J. Hern(cid:2)andez, “Numerical
InternationalConferenceonMachineLearning(PMLR,2018),pp.3208–3216. analysisofwindturbinewakes,”inProceedingsofWorkshoponWindEnergy
43Z.Long,Y.Lu,andB.Dong,“PDE-Net2.0:LearningPDEsfromdatawitha Applications(Delphi,Greece,1985),pp.15–25.
numeric-symbolichybriddeepnetwork,”J.Comput.Phys.399,108925(2019). 66R. Avva, C. Smith, and A. Singhal, “Comparative study of high and low
44H.Eivazi,H.Veisi,M.H.Naderi,andV.Esfahanian,“Deepneuralnetworks Reynolds number versions ofk-epsilon models,” in28th Aerospace Sciences
for nonlinear model order reduction of unsteady flows,” Phys. Fluids 32, Meeting,AIAAPaperNo.AIAA1990-0246,1990.
105104(2020). 67B.E.LaunderandD.B.Spalding,“Thenumericalcomputationofturbulent
45S.Hijazi,G.Stabile,A.Mola,andG.Rozza,“Data-drivenPOD-Galerkinreduced flows,”Comput.MethodsAppl.Mech.Eng.3,269–289(1974).
ordermodelforturbulentflows,”J.Comput.Phys.416,109513(2020). 68G. Kalitzin, G. Medic, G. Iaccarino, and P. Durbin, “Near-wall behavior of
46R.VinuesaandS.L.Brunton,“Enhancingcomputationalfluiddynamicswith RANS turbulence models and implications for wall functions,” J. Comput.
machinelearning,”Nat.Comput.Sci.2,358–366(2022). Phys.204,265–291(2005).
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-21
PublishedunderanexclusivelicensebyAIPPublishing
12
September
2026
13:02:35

| Physics | of Fluids |     |     |     |     | ARTICLE |     | pubs.aip.org/aip/pof |     |     |
| ------- | --------- | --- | --- | --- | --- | ------- | --- | -------------------- | --- | --- |
69B.Blocken,T.Stathopoulos,andJ.Carmeliet,“CFDsimulationoftheatmo- 82Y.-S.ChenandS.-W.Kim,“Computationofturbulentflowusinganextended
sphericboundarylayer:Wallfunctionproblems,”Atmos.Environ.41,238–252 turbulenceclosuremodel,”ReportNo.NASA-CR-179204(NASA,1987).
83A.ElKasmiandC.Masson,“Anextendedk–emodelforturbulentflowthrough
(2007).
70M.Abadi,A.Agarwal,P.Barham,E.Brevdo,Z.Chen,C.Citro,G.S.Corrado, horizontal-axiswindturbines,”J.WindEng.Ind.Aerodyn.96,103–122(2008).
A.Davis,J.Dean,M.Devin,S.Ghemawat,I.Goodfellow,A.Harp,G.Irving, 84J.M.HammersleyandD.C.Handscomb,MonteCarloMethods(Methuen&
M.Isard,Y.Jia,R.Jozefowicz,L.Kaiser,M.Kudlur,J.Levenberg,D.Man(cid:2)e,R. Co.Ltd.,London,1964),Vol.40,p.32.
85C.Wu,M.Zhu,Q.Tan,Y.Kartha,andL.Lu,“Acomprehensivestudyofnon-
| Monga, S. | Moore, D. | Murray, C. | Olah, M. Schuster, J. Shlens, | B. Steiner, I. |     |     |     |     |     |     |
| --------- | --------- | ---------- | ----------------------------- | -------------- | --- | --- | --- | --- | --- | --- |
Sutskever,K.Talwar,P.Tucker,V.Vanhoucke,V.Vasudevan,F.Vi(cid:2)egas,O.
|     |     |     |     |     | adaptive | and residual-based | adaptive | sampling | for physics-informed | neural |
| --- | --- | --- | --- | --- | -------- | ------------------ | -------- | -------- | -------------------- | ------ |
Vinyals,P.Warden,M.Wattenberg,M.Wicke,Y.Yu,andX.Zheng,seeten- networks,”Comput.MethodsAppl.Mech.Eng.403,115671(2023).
sorflow.orgfor“TensorFlow:Large-ScaleMachineLearningonHeterogeneous 86L.Vermeer,J.N.Sørensen,andA.Crespo,“Windturbinewakeaerodynamics,”
| Systems”(2015). |     |     |     |     | Prog.Aerosp.Sci.39,467–510(2003). |     |     |     |     |     |
| --------------- | --- | --- | --- | --- | --------------------------------- | --- | --- | --- | --- | --- |
71J.Rishi,A.Gafoor,S.Kumar,andD.Subramani,“Onthetrainingefficiencyof 87Y.-T.WuandF.Port(cid:2)e-Agel,“Atmosphericturbulenceeffectsonwind-turbine
|     |     |     | neuralnetworks,”inInternational |     | wakes:AnLESstudy,”Energies5,5340–5362(2012). |     |     |     |     |     |
| --- | --- | --- | ------------------------------- | --- | -------------------------------------------- | --- | --- | --- | --- | --- |
shallowarchitecturesforphysicsinformed
ConferenceonComputationalScience(Springer,2024),pp.363–377. 88P.K.Jha,E.P.N.Duque,J.L.Bashioum,andS.Schmitz,“Unravelingthemys-
72L. Biewald, see wandb.com. for “Experiment Tracking with Weights and teriesofturbulencetransportinawindfarm,”Energies8,6468–6496(2015).
Biases”(2020). 89A.Parente,C.Gorl(cid:2)e,J.VanBeeck,andC.Benocci,“Improvedk–emodeland
73D.V.Dung,N.D.Song,P.S.Palar,andL.R.Zuhal,“Onthechoiceofactiva- flows,”
|     |     |     |     |     | wall function | formulation | for the | RANS simulation | of ABL | J. Wind |
| --- | --- | --- | --- | --- | ------------- | ----------- | ------- | --------------- | ------ | ------- |
tionfunctionsinphysics-informedneuralnetworkforsolvingincompressible Eng.Ind.Aerodyn.99,267–278(2011).
fluidflows,”AIAAPaperNo.2023-1803,2023. 90J.W.Cleijne,“Resultsofsexbierumwindfarm:Singlewakemeasurements,”
74D.P.Kingma,“Adam:Amethodforstochasticoptimization,”arXiv:1412.6980 Technical Report No. 93–082 (TNO Environmental and Energy Research,
| (2014).                                                                 |     |     |     |     | Apeldoorn,Netherlands,1993). |                   |     |        |                    |             |
| ----------------------------------------------------------------------- | --- | --- | --- | --- | ---------------------------- | ----------------- | --- | ------ | ------------------ | ----------- |
| 75X.GlorotandY.Bengio,“Understandingthedifficultyoftrainingdeepfeedfor- |     |     |     |     | 91G.                         |                   |     |        |                    |             |
|                                                                         |     |     |     |     | J. Taylor,                   | Wake Measurements |     | on the | Nibe Wind-Turbines | in Denmark: |
ward neural networks,” in Proceedings of the Thirteenth International Data Collection and Analysis,Part 2 (National Power, Technology and
Conference on Artificial Intelligence and Statistics (JMLR Workshop and EnvironmentCentre,1990).
ConferenceProceedings,2010),pp.249–256. 92Siemens Digital Industries Software, Simcenter STAR-CCMþ CFD Software
| 76A.   |         | “quest-lab-iisc/PINN_WakeTurbulenceModel: |     | 2.0,” |                |     |     |     |     |     |
| ------ | ------- | ----------------------------------------- | --- | ----- | -------------- | --- | --- | --- | --- | --- |
| G. CTP | (2024). |                                           |     | V     | (Siemens2021). |     |     |     |     |     |
93D.
Zenodo.https://github.com/quest-lab-iisc/PINN_WakeTurbulenceModel C. Wilcox et al., Turbulence Modeling for CFD (DCW Industries, La
77J.Kim,P.Moin,andR.Moser,“Turbulencestatisticsinfullydevelopedchannel Canada,CA,1998),Vol.2.
flowatlowReynoldsnumber,”J.FluidMech.177,133–166(1987). 94F.R.Menter,“Two-equationeddy-viscosityturbulencemodelsforengineering
78R.D.Moser,J.Kim,andN.N.Mansour,“Directnumericalsimulationoftur- applications,”AIAAJ.32,1598–1605(1994).
bulentchannelflowuptoRes¼590,”Phys.Fluids11,943–945(1999). 95R. Jaw,“Second-order  12 September 2026 13:02:35
|     |     |     |     |     | R.Hwang | andS.-Y. |     |     | closure turbulence | models: Their |
| --- | --- | --- | --- | --- | ------- | -------- | --- | --- | ------------------ | ------------- |
79P.J.RichardsandR.P.Hoxey,“Appropriateboundaryconditionsforcompu- achievementsandlimitations,”Proc.Natl.Sci.Counc.,Repub.China,PartA
| tational wind | engineering | models | using the k-e turbulence | model,” J. Wind | 22,703–722(1998). |     |     |     |     |     |
| ------------- | ----------- | ------ | ------------------------ | --------------- | ----------------- | --- | --- | --- | --- | --- |
Eng.Ind.Aerodyn.46–47,145–153(1993). 96B.E.LaunderandN.Shima,“Second-momentclosureforthenear-wallsub-
80R.E.Froude,“Onthepartplayedinpropulsionbydifferencesoffluidpres- layer:Developmentandapplication,”AIAAJ.27,1319–1325(1989).
sure,”Trans.Inst.NavalArchitects30,390(1889). 97E.G.Antonini,D.A.Romero,andC.H.Amon,“Analysisandmodificationsof
81J.N.SørensenandA.Myken,“Unsteadyactuatordiscmodelforhorizontalaxis
turbulencemodelsforwindturbinewakesimulationsinatmosphericboundary
windturbines,”J.WindEng.Ind.Aerodyn.39,139–149(1992). layers,”J.Sol.EnergyEng.140,031007(2018).
Phys.Fluids37,015110(2025);doi:10.1063/5.0245113 37,015110-22
PublishedunderanexclusivelicensebyAIPPublishing
