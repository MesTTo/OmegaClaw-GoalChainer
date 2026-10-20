/- Purpose: transcribe tests/planning_oracle.py's finite planning model executably and prove, under the
agreed soundness contract (c-jk-pc-agreed-1019), that its K0 settle terminates, that the planner's knowledge
comes only from checked readings and what every world they admit entails, that a plan the repaired planner
accepts holds in every world the readings admit and has one at every turn, that every world's settling
ends, and that each rule of the contract is needed; its main compares the model with the oracle's
recorded answers. -/
-- am[implements a-jk-pf-lean-model-1019@bf3074]
import Mathlib.Algebra.BigOperators.Group.Finset.Basic
import Mathlib.Data.Finset.Card
import Mathlib.Data.Finset.Union
import Mathlib.Logic.Relation
import Lean.Data.Json

namespace GoalChainerPlanningModel

/-! ## Literals

A literal is a signal's index and the value it asserts, planning_oracle's `Lit` with signals numbered. -/

-- am[implements a-jk-pf-lean-model-1019@bf3074]
abbrev Lit := ℕ × Bool

-- The literal a world holds where `l` does not.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def neg (l : Lit) : Lit := (l.1, !l.2)

-- am[implements a-jk-pf-lean-model-1019@bf3074]
@[simp] theorem neg_fst (l : Lit) : (neg l).1 = l.1 := rfl
-- am[implements a-jk-pf-lean-model-1019@bf3074]
@[simp] theorem neg_neg (l : Lit) : neg (neg l) = l := by simp [neg]

-- Two literals of one signal are equal or opposite.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem eq_or_neg {l x : Lit} (h : x.1 = l.1) : x = l ∨ x = neg l := by
  rcases l with ⟨s, v⟩; rcases x with ⟨t, w⟩
  simp only at h; subst h
  cases v <;> cases w <;> simp [neg]

-- At most one value per signal: every state the oracle builds has it, written keeps it.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Functional (K : Finset Lit) : Prop := ∀ s v w, (s, v) ∈ K → (s, w) ∈ K → v = w

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem Functional.eq {K : Finset Lit} (hK : Functional K) {x y : Lit} (hx : x ∈ K) (hy : y ∈ K)
    (h : x.1 = y.1) : x = y := by
  rcases x with ⟨s, v⟩; rcases y with ⟨t, w⟩
  simp only at h; subst h
  rw [hK s v w hx hy]

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem Functional.not_neg {K : Finset Lit} (hK : Functional K) {l : Lit} (hl : l ∈ K) : neg l ∉ K := by
  intro hn
  have := hK.eq hl hn rfl
  rcases l with ⟨s, v⟩
  cases v <;> simp [neg] at this

-- One write of planning_oracle's `written`: `l` replaces whatever `K` held for its signal.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def write1 (K : Finset Lit) (l : Lit) : Finset Lit := insert l (K.filter (fun x => x.1 ≠ l.1))

-- planning_oracle's `written`: dict(known) updated with `L` in order, the last write of a signal winning.
-- Time: one filter of K per literal of L.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def written (K : Finset Lit) (L : List Lit) : Finset Lit := L.foldl write1 K

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem mem_write1 {K : Finset Lit} {l x : Lit} : x ∈ write1 K l ↔ x = l ∨ (x ∈ K ∧ x.1 ≠ l.1) := by
  simp [write1]

-- am[implements a-jk-pf-lean-model-1019@bf3074]
@[simp] theorem written_nil (K : Finset Lit) : written K [] = K := rfl

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem written_cons (K : Finset Lit) (l : Lit) (L : List Lit) :
    written K (l :: L) = written (write1 K l) L := rfl

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem mem_written {K : Finset Lit} {L : List Lit} {x : Lit} :
    x ∈ written K L → x ∈ K ∨ x ∈ L := by
  induction L generalizing K with
  | nil => exact Or.inl
  | cons l L ih =>
    intro h
    rcases ih h with h | h
    · rcases mem_write1.1 h with rfl | ⟨h, -⟩
      · exact Or.inr List.mem_cons_self
      · exact Or.inl h
    · exact Or.inr (List.mem_cons_of_mem _ h)

-- A literal survives every write that agrees with it or names another signal.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem mem_written_keep {K : Finset Lit} {L : List Lit} {x : Lit} (hx : x ∈ K)
    (h : ∀ w ∈ L, w.1 = x.1 → w = x) : x ∈ written K L := by
  induction L generalizing K with
  | nil => exact hx
  | cons l L ih =>
    refine ih ?_ (fun w hw => h w (List.mem_cons_of_mem _ hw))
    by_cases e : l.1 = x.1
    · rw [h l List.mem_cons_self e] at *
      exact mem_write1.2 (Or.inl rfl)
    · exact mem_write1.2 (Or.inr ⟨hx, fun h' => e h'.symm⟩)

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem written_mono {K K' : Finset Lit} (h : K ⊆ K') (L : List Lit) : written K L ⊆ written K' L := by
  induction L generalizing K K' with
  | nil => exact h
  | cons l L ih =>
    refine ih ?_
    intro x hx
    rcases mem_write1.1 hx with rfl | ⟨hx, e⟩
    · exact mem_write1.2 (Or.inl rfl)
    · exact mem_write1.2 (Or.inr ⟨h hx, e⟩)

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem functional_write1 {K : Finset Lit} (hK : Functional K) (l : Lit) : Functional (write1 K l) := by
  intro s v w hv hw
  rcases mem_write1.1 hv with hv | ⟨hv, ev⟩ <;> rcases mem_write1.1 hw with hw | ⟨hw, ew⟩
  · have := hv.trans hw.symm
    simp only [Prod.mk.injEq] at this
    exact this.2
  · exact absurd (congrArg Prod.fst hv) ew
  · exact absurd (congrArg Prod.fst hw) ev
  · exact hK s v w hv hw

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem functional_written {K : Finset Lit} (hK : Functional K) (L : List Lit) :
    Functional (written K L) := by
  induction L generalizing K with
  | nil => exact hK
  | cons l L ih => exact ih (functional_write1 hK l)

-- Where every write of signal `s` is already held, writing changes nothing about `s`.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem written_value {K : Finset Lit} {L : List Lit} (hK : Functional K) (s : ℕ) (v : Bool)
    (h : ∀ w ∈ L, w.1 = s → w ∈ K) : (s, v) ∈ written K L ↔ (s, v) ∈ K := by
  induction L generalizing K with
  | nil => rfl
  | cons l L ih =>
    have hK' := functional_write1 hK l
    have h' : ∀ w ∈ L, w.1 = s → w ∈ write1 K l := by
      intro w hw ew
      have hw' := h w (List.mem_cons_of_mem _ hw) ew
      by_cases e : l.1 = s
      · have hl := h l List.mem_cons_self e
        exact mem_write1.2 (Or.inl (hK.eq hw' hl (ew.trans e.symm)))
      · exact mem_write1.2 (Or.inr ⟨hw', fun h' => e (h'.symm.trans ew)⟩)
    rw [written_cons, ih hK' h', mem_write1]
    by_cases e : l.1 = s
    · have hl := h l List.mem_cons_self e
      constructor
      · rintro (hx | ⟨hx, -⟩)
        · rw [hx]; exact hl
        · exact hx
      · intro hx
        exact Or.inl (hK.eq hx hl e.symm)
    · constructor
      · rintro (hx | ⟨hx, -⟩)
        · exact absurd (congrArg Prod.fst hx).symm e
        · exact hx
      · intro hx; exact Or.inr ⟨hx, fun h' => e h'.symm⟩

-- Writing what is already held, consistently, changes nothing.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem written_eq_self {K : Finset Lit} {L : List Lit} (hK : Functional K) (h : ∀ w ∈ L, w ∈ K) :
    written K L = K := by
  ext ⟨s, v⟩
  exact written_value hK s v (fun w hw _ => h w hw)

-- A literal of a signal no write names keeps its membership.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem written_other {K : Finset Lit} {L : List Lit} {x : Lit} (h : ∀ w ∈ L, w.1 ≠ x.1) :
    x ∈ written K L ↔ x ∈ K := by
  induction L generalizing K with
  | nil => rfl
  | cons l L ih =>
    rw [written_cons, ih (fun w hw => h w (List.mem_cons_of_mem _ hw)), mem_write1]
    have e := h l List.mem_cons_self
    constructor
    · rintro (hx | ⟨hx, -⟩)
      · exact absurd (by rw [hx]) e
      · exact hx
    · intro hx; exact Or.inr ⟨hx, fun h' => e h'.symm⟩

-- Each literal of `L` is held after writing `L` unless a later write of its signal disagrees.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem mem_written_last {K : Finset Lit} {L : List Lit} {x : Lit} (hx : x ∈ L)
    (h : ∀ w ∈ L, w.1 = x.1 → w = x) : x ∈ written K L := by
  induction L generalizing K with
  | nil => simp at hx
  | cons l L ih =>
    rw [written_cons]
    by_cases hxL : x ∈ L
    · exact ih hxL (fun w hw => h w (List.mem_cons_of_mem _ hw))
    · have : x = l := by
        rcases List.mem_cons.1 hx with hx | hx
        · exact hx
        · exact absurd hx hxL
      subst this
      exact mem_written_keep (mem_write1.2 (Or.inl rfl)) (fun w hw => h w (List.mem_cons_of_mem _ hw))

/-! ## The library

A library as the model reads it: procedures over numbered signals, steps and actions, and each action's
reaction as (the literal its redex reads, the literal its reactum writes). -/

-- am[implements a-jk-pf-lean-model-1019@bf3074]
inductive StepKind where
  | achieve (literal : Lit)
  | act (action : ℕ)
  | investigate
  deriving DecidableEq, Repr

-- am[implements a-jk-pf-lean-model-1019@bf3074]
structure Step where
  id : ℕ
  kind : StepKind
  after : List ℕ
  deriving DecidableEq, Repr

-- am[implements a-jk-pf-lean-model-1019@bf3074]
structure Procedure where
  achieves : List Lit
  when : List Lit
  steps : List Step
  deriving DecidableEq, Repr

-- am[implements a-jk-pf-lean-model-1019@bf3074]
structure Library where
  procedures : List Procedure
  reactions : List (ℕ × Lit × Lit)
  deriving DecidableEq, Repr

-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Step.executed (s : Step) : Bool :=
  match s.kind with
  | .achieve _ => false
  | _ => true

-- planning_oracle's Model.reach walk as a closure: from `ids` through After, an executed step is reached
-- and stops the walk, an Achieve step continues to its own After.
-- Time: at most a + 1 rounds, a the total length of the steps' After lists, each a pass over the steps.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def reached (steps : List Step) (ids : List ℕ) : Finset ℕ :=
  let expand (R : Finset ℕ) : Finset ℕ :=
    R ∪ (steps.filter (fun s => s.id ∈ R && !s.executed)).foldr (fun s acc => acc ∪ s.after.toFinset) ∅
  expand^[(steps.map (·.after.length)).sum + 1] ids.toFinset

-- Model.reach: the executed steps the walk reaches and the literals of the Achieve steps it passes.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def reach (steps : List Step) (ids : List ℕ) : Finset ℕ × Finset Lit :=
  let R := reached steps ids
  (((steps.filter (fun s => s.id ∈ R && s.executed)).map (·.id)).toFinset,
   (steps.filterMap (fun s =>
      if s.id ∈ R then
        (match s.kind with
         | .achieve l => some l
         | _ => none)
      else none)).toFinset)

-- Model.terminal: the steps no After names.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def terminal (steps : List Step) : List ℕ :=
  (steps.filter (fun s => s.id ∉ steps.flatMap (·.after))).map (·.id)

/-- What the model reads of a library, procedure by procedure: Model.reads, executed_steps, when,
achieves, each step's reach through After, and Model.reaction. Every theorem below holds for every
`Rules`, so for every library `Library.compile` reads. -/
-- am[implements a-jk-pf-lean-model-1019@bf3074]
structure Rules where
  count : ℕ
  derive : ℕ → Bool
  when : ℕ → Finset Lit
  achieves : ℕ → List Lit
  needs : ℕ → Finset ℕ
  reads : ℕ → Finset Lit
  steps : ℕ → List ℕ
  before : ℕ → ℕ → Finset ℕ
  beforeLits : ℕ → ℕ → Finset Lit
  reaction : ℕ → ℕ → Option (Lit × Lit)

-- The procedure a library declares at `i`, or an empty one past its end, which nothing iterates.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Library.procedure (lib : Library) (i : ℕ) : Procedure := lib.procedures.getD i ⟨[], [], []⟩

-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Library.stepOf (lib : Library) (i e : ℕ) : Option Step := (lib.procedure i).steps.find? (·.id == e)

-- Model.reads, Model.reaction and the reach of each step, read off the library once.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Library.compile (lib : Library) : Rules where
  count := lib.procedures.length
  derive i := !((lib.procedure i).steps.any Step.executed)
  when i := (lib.procedure i).when.toFinset
  achieves i := (lib.procedure i).achieves
  needs i :=
    let p := lib.procedure i
    if p.steps.any Step.executed then (reach p.steps (terminal p.steps)).1 else ∅
  reads i :=
    let p := lib.procedure i
    if p.steps.any Step.executed then (reach p.steps (terminal p.steps)).2
    else p.when.toFinset ∪ (reach p.steps (p.steps.map (·.id))).2
  steps i := ((lib.procedure i).steps.filter Step.executed).map (·.id)
  before i e :=
    match lib.stepOf i e with
    | some s => (reach (lib.procedure i).steps s.after).1
    | none => ∅
  beforeLits i e :=
    match lib.stepOf i e with
    | some s => (reach (lib.procedure i).steps s.after).2
    | none => ∅
  reaction i e :=
    match lib.stepOf i e with
    | some ⟨_, .act a, _⟩ => (lib.reactions.find? (·.1 == a)).map (·.2)
    | _ => none

/-! ## States

planning_oracle's State with each procedure's instance in one status, so an instance is never both
open and uncertain. `completed` is the observed snapshot's status for a journal instance every admitted
world finished before the readings, whose Finish only journals it (a-jk-pc-r3-exact-amend-1019). -/

-- am[implements a-jk-pf-lean-model-1019@bf3074]
inductive Inst where
  | closed
  | opened (done : Finset ℕ)
  | uncertain (done : Finset ℕ)
  | completed
  deriving DecidableEq

-- am[implements a-jk-pf-lean-model-1019@bf3074]
structure State where
  known : Finset Lit
  inst : ℕ → Inst
  changed : Finset ℕ
  inflight : Finset (ℕ × ℕ)

-- State.dispatched: the steps of `i`'s instance in flight.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def State.dispatched (S : State) (i : ℕ) : Finset ℕ := (S.inflight.filter (·.1 = i)).image Prod.snd

-- am[implements a-jk-pf-lean-model-1019@bf3074]
theorem mem_dispatched {S : State} {i e : ℕ} : e ∈ S.dispatched i ↔ (i, e) ∈ S.inflight := by
  unfold State.dispatched
  simp only [Finset.mem_image, Finset.mem_filter]
  constructor
  · rintro ⟨a, ⟨ha, hi⟩, he⟩
    have : a = (i, e) := Prod.ext hi he
    rw [← this]; exact ha
  · intro h; exact ⟨(i, e), ⟨h, rfl⟩, rfl⟩

-- State.possibly: no literal of `L` is known false.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def possibly (K L : Finset Lit) : Prop := ∀ l ∈ L, neg l ∉ K

-- am[implements a-jk-pf-lean-model-1019@bf3074]
instance (K L : Finset Lit) : Decidable (possibly K L) :=
  inferInstanceAs (Decidable (∀ l ∈ L, neg l ∉ K))

/-! ## The K0 settle

Model.settle: one round collects the maybe items, Finish and Derive whose reads possibly hold without
all being known and the acts in flight, and each item's writes forget the opposite literal where the
item reads a moved signal or the written signal has moved. A round never adds knowledge, so rounds
repeat until one changes nothing. -/

-- A procedure's Achieves as a maybe item of `S`, with whether it reads a moved signal; none if it is no
-- item. A Finish of an open instance reads its own Done markers, which a step wrote, so it is moved.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def item (R : Rules) (S : State) (i : ℕ) : Option Bool :=
  if possibly S.known (R.reads i) then
    if R.derive i then
      if R.reads i ⊆ S.known then none else some (decide (∃ l ∈ R.reads i, l.1 ∈ S.changed))
    else
      match S.inst i with
      | .opened D =>
        if R.needs i ⊆ D ∪ S.dispatched i ∧ ¬(R.needs i ⊆ D ∧ R.reads i ⊆ S.known) then some true
        else none
      | .uncertain _ => some true
      | _ => none
  else none

-- Procedure `i`'s writes a round processes.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def itemHits (R : Rules) (S : State) (i : ℕ) : Finset Lit :=
  match item R S i with
  | none => ∅
  | some mv => (R.achieves i).toFinset.filter (fun w => w ∉ S.known ∧ (mv = true ∨ w.1 ∈ S.changed))

-- An act in flight's reaction write a round processes, always moved.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def actHits (R : Rules) (S : State) (a : ℕ × ℕ) : Finset Lit :=
  match R.reaction a.1 a.2 with
  | none => ∅
  | some r => if r.2 ∈ S.known then ∅ else {r.2}

-- The writes a round processes: each item's writes it does not know, where the item moved or the
-- signal has; and each act in flight's reaction write.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def hits (R : Rules) (S : State) : Finset Lit :=
  (Finset.range R.count).biUnion (itemHits R S) ∪ S.inflight.biUnion (actHits R S)

-- An open instance whose Finish is a maybe item becomes uncertain: some world has finished it.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def movesB (R : Rules) (S : State) (i : ℕ) : Bool :=
  decide (i < R.count) && !R.derive i && decide (possibly S.known (R.reads i)) &&
  match S.inst i with
  | .opened D => decide (R.needs i ⊆ D ∪ S.dispatched i ∧ ¬(R.needs i ⊆ D ∧ R.reads i ⊆ S.known))
  | _ => false

-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Inst.toUncertain : Inst → Inst
  | .opened D => .uncertain D
  | x => x

-- One pass of Model.settle's loop.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def round (R : Rules) (S : State) : State where
  known := S.known.filter (fun l => neg l ∉ hits R S)
  inst i := if movesB R S i then (S.inst i).toUncertain else S.inst i
  changed := S.changed ∪ (hits R S).image Prod.fst
  inflight := S.inflight

-- A round that changes nothing: every processed write's opposite already unknown and its signal moved,
-- and no instance to make uncertain.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Stable (R : Rules) (S : State) : Prop :=
  (∀ w ∈ hits R S, neg w ∉ S.known ∧ w.1 ∈ S.changed) ∧ ∀ i ∈ Finset.range R.count, movesB R S i = false

-- am[implements a-jk-pf-lean-model-1019@bf3074]
instance (R : Rules) (S : State) : Decidable (Stable R S) :=
  inferInstanceAs (Decidable ((∀ w ∈ hits R S, neg w ∉ S.known ∧ w.1 ∈ S.changed) ∧
    ∀ i ∈ Finset.range R.count, movesB R S i = false))

-- The signals any round of `S` can move: the procedures' Achieves and the reactions of the acts in
-- flight, which no round changes.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def moveable (R : Rules) (S : State) : Finset ℕ :=
  (Finset.range R.count).biUnion (fun i => (R.achieves i).toFinset.image Prod.fst) ∪
  S.inflight.biUnion (fun a =>
    match R.reaction a.1 a.2 with
    | none => ∅
    | some r => {r.2.1})

-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Inst.isOpened : Inst → Bool
  | .opened _ => true
  | _ => false

-- am[implements a-jk-pf-lean-model-1019@bf3074]
def openCount (R : Rules) (S : State) : ℕ :=
  ((Finset.range R.count).filter (fun i => (S.inst i).isOpened)).card

-- What only falls while a round changes something: known literals, open instances and unmoved signals.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def measure (R : Rules) (S : State) : ℕ :=
  S.known.card + openCount R S + (moveable R S \ S.changed).card

-- Rounds until one changes nothing, at most `n` of them.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def settleFuel (R : Rules) : ℕ → State → State
  | 0, S => S
  | n + 1, S => if Stable R S then S else settleFuel R n (round R S)

-- Model.settle. Time: at most measure + 1 rounds, measure at most k + p + c for k known literals,
-- p procedures and c moveable signals, each round one item per procedure and act in flight.
-- am[implements a-jk-pf-lean-model-1019@bf3074] am[implements a-jk-pf-finite-1019@ef14d4]
def settle (R : Rules) (S : State) : State := settleFuel R (measure R S + 1) S

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem mem_itemHits {R : Rules} {S : State} {i : ℕ} {w : Lit} :
    w ∈ itemHits R S i ↔ ∃ mv, item R S i = some mv ∧ w ∈ R.achieves i ∧ w ∉ S.known ∧
      (mv = true ∨ w.1 ∈ S.changed) := by
  unfold itemHits
  cases item R S i with
  | none => simp
  | some mv => simp

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem mem_actHits {R : Rules} {S : State} {a : ℕ × ℕ} {w : Lit} :
    w ∈ actHits R S a ↔ ∃ r, R.reaction a.1 a.2 = some r ∧ r.2 = w ∧ w ∉ S.known := by
  unfold actHits
  cases R.reaction a.1 a.2 with
  | none => simp
  | some r =>
    by_cases k : r.2 ∈ S.known
    · simp only [k, if_true, Finset.notMem_empty, Option.some.injEq, false_iff, not_exists, not_and]
      intro r' e e'; subst e; subst e'; exact fun h => h k
    · simp only [k, if_false, Finset.mem_singleton, Option.some.injEq]
      constructor
      · rintro rfl; exact ⟨r, rfl, rfl, k⟩
      · rintro ⟨r', rfl, rfl, -⟩; rfl

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem hits_mem {R : Rules} {S : State} {w : Lit} :
    w ∈ hits R S ↔ (∃ i < R.count, w ∈ itemHits R S i) ∨ (∃ a ∈ S.inflight, w ∈ actHits R S a) := by
  simp [hits]

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem hits_fst_moveable {R : Rules} {S : State} {w : Lit} (h : w ∈ hits R S) : w.1 ∈ moveable R S := by
  unfold moveable
  rcases hits_mem.1 h with ⟨i, hi, h⟩ | ⟨a, ha, h⟩
  · obtain ⟨mv, -, hw, -, -⟩ := mem_itemHits.1 h
    exact Finset.mem_union_left _ (Finset.mem_biUnion.2
      ⟨i, Finset.mem_range.2 hi, Finset.mem_image.2 ⟨w, List.mem_toFinset.2 hw, rfl⟩⟩)
  · obtain ⟨r, er, rfl, -⟩ := mem_actHits.1 h
    exact Finset.mem_union_right _ (Finset.mem_biUnion.2 ⟨a, ha, by rw [er]; simp⟩)

-- am[implements a-jk-pf-finite-1019@ef14d4]
@[simp] theorem round_inflight (R : Rules) (S : State) : (round R S).inflight = S.inflight := rfl

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem moveable_round (R : Rules) (S : State) : moveable R (round R S) = moveable R S := rfl

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem round_known_subset (R : Rules) (S : State) : (round R S).known ⊆ S.known := Finset.filter_subset _ _

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem round_changed_superset (R : Rules) (S : State) : S.changed ⊆ (round R S).changed :=
  Finset.subset_union_left

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem movesB_opened {R : Rules} {S : State} {i : ℕ} (h : movesB R S i = true) :
    ∃ D, S.inst i = .opened D := by
  unfold movesB at h
  cases e : S.inst i with
  | opened D => exact ⟨D, rfl⟩
  | _ => simp [e] at h

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem round_inst_eq (R : Rules) (S : State) (i : ℕ) :
    (round R S).inst i = if movesB R S i then (S.inst i).toUncertain else S.inst i := rfl

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem round_inst (R : Rules) (S : State) (i : ℕ) :
    (round R S).inst i = S.inst i ∨ ∃ D, S.inst i = .opened D ∧ (round R S).inst i = .uncertain D := by
  rw [round_inst_eq]
  by_cases h : movesB R S i
  · obtain ⟨D, e⟩ := movesB_opened h
    right; exact ⟨D, e, by simp [h, e, Inst.toUncertain]⟩
  · left; simp [h]

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem stable_round_eq {R : Rules} {S : State} (h : Stable R S) : round R S = S := by
  obtain ⟨hw, hi⟩ := h
  cases S with
  | mk known inst changed inflight =>
    simp only [round, State.mk.injEq, and_true]
    refine ⟨?_, ?_, ?_⟩
    · apply Finset.filter_true_of_mem
      intro l hl hn
      exact (hw (neg l) hn).1 (by simpa using hl)
    · funext i
      by_cases hc : i < R.count
      · simp [hi i (Finset.mem_range.2 hc)]
      · have : movesB R ⟨known, inst, changed, inflight⟩ i = false := by simp [movesB, hc]
        simp [this]
    · apply Finset.union_eq_left.2
      intro s hs
      obtain ⟨w, hw', rfl⟩ := Finset.mem_image.1 hs
      exact (hw w hw').2

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem openCount_round_le (R : Rules) (S : State) : openCount R (round R S) ≤ openCount R S := by
  apply Finset.card_le_card
  intro i hi
  obtain ⟨hr, ho⟩ := Finset.mem_filter.1 hi
  refine Finset.mem_filter.2 ⟨hr, ?_⟩
  rcases round_inst R S i with e | ⟨D, -, e⟩
  · rwa [e] at ho
  · rw [e] at ho; simp [Inst.isOpened] at ho

-- A round that changes something lowers the measure, so the settle's loop ends.
-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem measure_round_lt {R : Rules} {S : State} (h : ¬ Stable R S) : measure R (round R S) < measure R S := by
  have hk : (round R S).known.card ≤ S.known.card := Finset.card_le_card (round_known_subset R S)
  have ho := openCount_round_le R S
  have hsub : moveable R S \ (round R S).changed ⊆ moveable R S \ S.changed :=
    Finset.sdiff_subset_sdiff (Finset.Subset.refl _) (round_changed_superset R S)
  have hc : (moveable R (round R S) \ (round R S).changed).card ≤ (moveable R S \ S.changed).card := by
    rw [moveable_round]; exact Finset.card_le_card hsub
  unfold measure
  unfold Stable at h
  rw [not_and_or] at h
  rcases h with h | h
  · push Not at h
    obtain ⟨w, hw, hn⟩ := h
    by_cases hk' : neg w ∈ S.known
    · have : (round R S).known.card < S.known.card := by
        apply Finset.card_lt_card
        refine Finset.ssubset_iff_subset_ne.2 ⟨round_known_subset R S, fun e => ?_⟩
        have : neg w ∈ (round R S).known := e ▸ hk'
        exact (Finset.mem_filter.1 this).2 (by simpa using hw)
      omega
    · have hs : w.1 ∉ S.changed := hn hk'
      have : (moveable R (round R S) \ (round R S).changed).card < (moveable R S \ S.changed).card := by
        rw [moveable_round]
        apply Finset.card_lt_card
        refine Finset.ssubset_iff_subset_ne.2 ⟨hsub, fun e => ?_⟩
        have hin : w.1 ∈ moveable R S \ S.changed := Finset.mem_sdiff.2 ⟨hits_fst_moveable hw, hs⟩
        rw [← e] at hin
        exact (Finset.mem_sdiff.1 hin).2
          (Finset.mem_union_right _ (Finset.mem_image.2 ⟨w, hw, rfl⟩))
      omega
  · push Not at h
    obtain ⟨i, hi, hm⟩ := h
    have hm' : movesB R S i = true := by simpa using hm
    obtain ⟨D, e⟩ := movesB_opened hm'
    have : openCount R (round R S) < openCount R S := by
      apply Finset.card_lt_card
      refine Finset.ssubset_iff_subset_ne.2 ⟨?_, fun eq => ?_⟩
      · intro j hj
        obtain ⟨hr, ho⟩ := Finset.mem_filter.1 hj
        refine Finset.mem_filter.2 ⟨hr, ?_⟩
        rcases round_inst R S j with e' | ⟨D', -, e'⟩
        · rwa [e'] at ho
        · rw [e'] at ho; simp [Inst.isOpened] at ho
      · have hin : i ∈ (Finset.range R.count).filter (fun j => (S.inst j).isOpened) :=
          Finset.mem_filter.2 ⟨hi, by simp [e, Inst.isOpened]⟩
        rw [← eq] at hin
        have : (round R S).inst i = .uncertain D := by
          rw [round_inst_eq]; simp [hm', e, Inst.toUncertain]
        simp [this, Inst.isOpened] at hin
    omega

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem settleFuel_stable (R : Rules) : ∀ n S, measure R S < n → Stable R (settleFuel R n S)
  | 0, _, h => absurd h (Nat.not_lt_zero _)
  | n + 1, S, h => by
    simp only [settleFuel]
    split_ifs with hs
    · exact hs
    · exact settleFuel_stable R n _ (by have := measure_round_lt hs; omega)

-- The settle ends in a state no round changes (Model.settle's `following == state`).
-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem settle_stable (R : Rules) (S : State) : Stable R (settle R S) :=
  settleFuel_stable R _ S (Nat.lt_succ_self _)

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem settleFuel_iterate (R : Rules) :
    ∀ n S, ∃ k ≤ n, k ≤ measure R S ∧ settleFuel R n S = (round R)^[k] S
  | 0, S => ⟨0, le_refl _, Nat.zero_le _, rfl⟩
  | n + 1, S => by
    simp only [settleFuel]
    split_ifs with hs
    · exact ⟨0, Nat.zero_le _, Nat.zero_le _, rfl⟩
    · obtain ⟨k, hkn, hkm, e⟩ := settleFuel_iterate R n (round R S)
      refine ⟨k + 1, by omega, ?_, by rw [e, Function.iterate_succ_apply]⟩
      have := measure_round_lt hs
      omega

-- The settle is the round iterated at most `measure` times: at most k + p + c rounds, as Model.settle's
-- comment counts them.
-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem settle_rounds (R : Rules) (S : State) :
    ∃ k ≤ measure R S, settle R S = (round R)^[k] S := by
  obtain ⟨k, -, hk, e⟩ := settleFuel_iterate R (measure R S + 1) S
  exact ⟨k, hk, e⟩

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem settleFuel_props (R : Rules) (P : State → State → Prop) (hrefl : ∀ S, P S S)
    (htrans : ∀ S T, P (round R S) T → P S T) : ∀ n S, P S (settleFuel R n S)
  | 0, S => hrefl S
  | n + 1, S => by
    simp only [settleFuel]
    split_ifs
    · exact hrefl S
    · exact htrans S _ (settleFuel_props R P hrefl htrans n _)

-- The settle never adds knowledge.
-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem settle_known_subset (R : Rules) (S : State) : (settle R S).known ⊆ S.known :=
  settleFuel_props R (fun S T => T.known ⊆ S.known) (fun _ => Finset.Subset.refl _)
    (fun S _ h => h.trans (round_known_subset R S)) _ S

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem settle_changed_superset (R : Rules) (S : State) : S.changed ⊆ (settle R S).changed :=
  settleFuel_props R (fun S T => S.changed ⊆ T.changed) (fun _ => Finset.Subset.refl _)
    (fun S _ h => (round_changed_superset R S).trans h) _ S

-- am[implements a-jk-pf-finite-1019@ef14d4]
@[simp] theorem settle_inflight (R : Rules) (S : State) : (settle R S).inflight = S.inflight :=
  settleFuel_props R (fun S T => T.inflight = S.inflight) (fun _ => rfl) (fun _ _ h => h) _ S

-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem settle_inst (R : Rules) (S : State) (i : ℕ) :
    (settle R S).inst i = S.inst i ∨ ∃ D, S.inst i = .opened D ∧ (settle R S).inst i = .uncertain D := by
  refine settleFuel_props R
    (fun S T => T.inst i = S.inst i ∨ ∃ D, S.inst i = .opened D ∧ T.inst i = .uncertain D)
    (fun _ => Or.inl rfl) (fun S T h => ?_) _ S
  rcases round_inst R S i with e | ⟨D, eS, eR⟩ <;> rcases h with h | ⟨D', eS', eT⟩
  · exact Or.inl (h.trans e)
  · exact Or.inr ⟨D', e ▸ eS', eT⟩
  · exact Or.inr ⟨D, eS, h.trans eR⟩
  · rw [eR] at eS'; cases eS'

/-! ## Moves -/

-- am[implements a-jk-pf-lean-model-1019@bf3074]
inductive Part where
  | start
  | finish
  | derive
  | step (id : ℕ)
  deriving DecidableEq, Repr

-- am[implements a-jk-pf-lean-model-1019@bf3074]
structure Move where
  index : ℕ
  part : Part
  deriving DecidableEq, Repr

-- An act's reaction finds the literal its redex reads known; an investigation or an act with no
-- reaction reads nothing more.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def reactionReady (R : Rules) (S : State) (i e : ℕ) : Bool :=
  match R.reaction i e with
  | none => true
  | some r => decide (r.1 ∈ S.known)

-- Procedure `i`'s Finish or Derive if enabled: a Derive whose reads are known and whose Achieves are
-- not, an open instance's Finish whose needed steps are done and whose reads are known, and a completed
-- instance's journal-only Finish.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def priorityAt (R : Rules) (S : State) (i : ℕ) : List Move :=
  if R.derive i then
    (if R.reads i ⊆ S.known ∧ ¬ (R.achieves i).toFinset ⊆ S.known then [⟨i, .derive⟩] else [])
  else
    match S.inst i with
    | .opened D => if R.needs i ⊆ D ∧ R.reads i ⊆ S.known then [⟨i, .finish⟩] else []
    | .completed => [⟨i, .finish⟩]
    | _ => []

-- Finish and Derive, the priority class of Model.enabled.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def priority (R : Rules) (S : State) : List Move := (List.range R.count).flatMap (priorityAt R S)

-- Executed step `e` of `i`'s open instance, if enabled: not done, not in flight, When known, the walk back
-- from its After finding each executed step done and each Achieve literal known, and its reaction's read
-- known.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def stepReady (R : Rules) (S : State) (i : ℕ) (D : Finset ℕ) (e : ℕ) : Prop :=
  e ∉ D ∧ (i, e) ∉ S.inflight ∧ R.when i ⊆ S.known ∧ R.before i e ⊆ D ∧ R.beforeLits i e ⊆ S.known ∧
    reactionReady R S i e = true

-- am[implements a-jk-pf-lean-model-1019@bf3074]
instance (R : Rules) (S : State) (i : ℕ) (D : Finset ℕ) (e : ℕ) : Decidable (stepReady R S i D e) :=
  inferInstanceAs (Decidable (_ ∧ _))

-- Procedure `i`'s Start or executed steps if enabled.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def ordinaryAt (R : Rules) (S : State) (i : ℕ) : List Move :=
  if R.derive i then [] else
    match S.inst i with
    | .closed => if R.when i ⊆ S.known then [⟨i, .start⟩] else []
    | .opened D => ((R.steps i).filter (fun e => decide (stepReady R S i D e))).map (fun e => ⟨i, .step e⟩)
    | _ => []

-- Start and the executed steps, the class Model.enabled answers when no Finish or Derive is enabled.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def ordinary (R : Rules) (S : State) : List Move := (List.range R.count).flatMap (ordinaryAt R S)

-- Model.enabled.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def enabled (R : Rules) (S : State) : List Move :=
  match priority R S with
  | [] => ordinary R S
  | p => p

-- planning_oracle's _write: the literals written and their signals moved.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def write (S : State) (L : List Lit) : State :=
  { S with known := written S.known L, changed := S.changed ∪ (L.map Prod.fst).toFinset }

-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Inst.done : Inst → Finset ℕ
  | .opened D => D
  | .uncertain D => D
  | _ => ∅

-- Model.step: the state a move leaves, as a world takes it. A completed instance's Finish closes it and
-- writes nothing, its effects being observed or entailed already.
-- am[implements a-jk-pf-lean-model-1019@bf3074] am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
def step (R : Rules) (S : State) (m : Move) : State :=
  match m.part with
  | .start => { S with inst := Function.update S.inst m.index (.opened ∅) }
  | .step e =>
    let S' : State :=
      { S with inst := Function.update S.inst m.index (.opened (insert e (S.inst m.index).done)) }
    match R.reaction m.index e with
    | none => S'
    | some r => write S' [r.2]
  | .finish =>
    match S.inst m.index with
    | .completed => { S with inst := Function.update S.inst m.index .closed }
    | _ => { write S (R.achieves m.index) with
             inst := Function.update S.inst m.index .closed,
             inflight := S.inflight.filter (·.1 ≠ m.index) }
  | .derive => write S (R.achieves m.index)

-- The instance half of a landing: the act leaves the flight and its step is done if its instance is open.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def landed (S : State) (a : ℕ × ℕ) : State :=
  { S with
    inflight := S.inflight.erase a,
    inst := match S.inst a.1 with
      | .opened D => Function.update S.inst a.1 (.opened (insert a.2 D))
      | _ => S.inst }

-- Model.land: a world where an act in flight lands, its step done and its reaction applied over the state
-- as it stands.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def land (R : Rules) (S : State) (a : ℕ × ℕ) : State :=
  match R.reaction a.1 a.2 with
  | none => landed S a
  | some r => write (landed S a) [r.2]

-- Model.apply.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def apply (R : Rules) (S : State) (m : Move) : State := settle R (step R S m)

/-! ## The snapshot

The readings and the executor's journal as the model starts from them. -/

-- The estimators whose readings justification checks (planning_oracle's CHECKED_ESTIMATORS).
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def checkedEstimators : List String := ["deterministic", "measured", "human-asserted"]

-- am[implements a-jk-pf-lean-model-1019@bf3074]
structure Reading where
  signal : ℕ
  detected : Bool
  estimator : String
  deriving DecidableEq, Repr

-- planning_oracle's start_state: the literals checked readings observe and those an unchecked reading
-- only offers as assumptions.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def startState (rs : List Reading) : Finset Lit × Finset Lit :=
  let observed := rs.filter (fun r => r.estimator ∈ checkedEstimators)
  let assumable := rs.filter (fun r => r.estimator ∉ checkedEstimators)
  ((observed.map (fun r => (r.signal, r.detected))).toFinset,
   (assumable.map (fun r => (r.signal, r.detected))).toFinset)

-- am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
/-- How the readings classify the journal's open instances, and what they entail (R3, exact,
a-jk-pc-r3-exact-amend-1019): an instance `completes` is closed in every rest the readings admit, one
`keeps` is open in every such rest, and every such rest holds the `entailed` literals, a completed
instance's Achieves among them. planning_oracle.observe computes the exact classification by enumerating
those rests; `Observation.Sound` below says what any classification must bear out. -/
structure Observation where
  completes : ℕ → Bool
  keeps : ℕ → Bool
  entailed : Finset Lit

-- planning_oracle.observe with the classification `o`: a completed instance is closed only by a
-- journal-only Finish and its acts in flight drop, a kept one stays open, any other open one is
-- uncertain, and the entailed literals join what was observed as a reading does, before the settle
-- (c-jk-pc-entailed-as-observation-1019).
-- am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
def observeWith (S : State) (o : Observation) : State :=
  { S with
    known := S.known ∪ o.entailed,
    inst := fun i => match S.inst i with
      | .opened D => if o.completes i then .completed else if o.keeps i then .opened D else .uncertain D
      | other => other,
    inflight := S.inflight.filter (fun a => !o.completes a.1) }

-- planning_oracle's observing: an investigator's answer is a reading of the snapshot, replacing what was
-- observed of its signal.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def observing (S : State) (s : ℕ) (v : Bool) : State := { S with known := written S.known [(s, v)] }

/-! ## Separation

Knowledge comes only from checked readings and what every world they admit entails: neither the journal,
nor a receipt, nor the settle, nor an act in flight adds a literal by itself, and every move reads only
what is known. -/

-- Only a checked reading observes a literal; an unchecked one is only ever an assumption.
-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem startState_observed (rs : List Reading) (l : Lit) :
    l ∈ (startState rs).1 ↔ ∃ r ∈ rs, r.estimator ∈ checkedEstimators ∧ (r.signal, r.detected) = l := by
  simp [startState, and_assoc]

-- The model's starting knowledge is within the checked readings and the observation's entailed literals,
-- whatever the journal says.
-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem journal_sets_no_literal (R : Rules) (K : Finset Lit) (inst : ℕ → Inst) (F : Finset (ℕ × ℕ))
    (o : Observation) : (settle R (observeWith ⟨K, inst, ∅, F⟩ o)).known ⊆ K ∪ o.entailed :=
  settle_known_subset R _

-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem mem_priorityAt {R : Rules} {S : State} {i : ℕ} {m : Move} :
    m ∈ priorityAt R S i ↔ m.index = i ∧
      ((R.derive i = true ∧ m.part = .derive ∧ R.reads i ⊆ S.known ∧ ¬ (R.achieves i).toFinset ⊆ S.known) ∨
       (R.derive i = false ∧ m.part = .finish ∧
          ((∃ D, S.inst i = .opened D ∧ R.needs i ⊆ D ∧ R.reads i ⊆ S.known) ∨ S.inst i = .completed))) := by
  rcases m with ⟨j, p⟩
  by_cases hd : R.derive i = true
  · have e : priorityAt R S i =
        (if R.reads i ⊆ S.known ∧ ¬ (R.achieves i).toFinset ⊆ S.known then [⟨i, .derive⟩] else []) := by
      simp [priorityAt, hd]
    rw [e]
    by_cases hc : R.reads i ⊆ S.known ∧ ¬ (R.achieves i).toFinset ⊆ S.known
    · rw [if_pos hc]
      simp only [List.mem_singleton, Move.mk.injEq]
      constructor
      · rintro ⟨rfl, rfl⟩; exact ⟨rfl, Or.inl ⟨hd, rfl, hc⟩⟩
      · rintro ⟨rfl, h⟩
        rcases h with ⟨-, rfl, -⟩ | ⟨h, -⟩
        · exact ⟨rfl, rfl⟩
        · rw [hd] at h; cases h
    · rw [if_neg hc]
      simp only [List.not_mem_nil, false_iff, not_and]
      rintro rfl h
      rcases h with ⟨-, -, h⟩ | ⟨h, -⟩
      · exact hc h
      · rw [hd] at h; cases h
  · have hd' : R.derive i = false := by simpa using hd
    cases hi : S.inst i with
    | closed =>
      have e : priorityAt R S i = [] := by simp [priorityAt, hd', hi]
      rw [e]
      simp only [List.not_mem_nil, false_iff, not_and]
      rintro rfl h
      rcases h with ⟨h, -⟩ | ⟨-, -, ⟨D, h, -⟩ | h⟩
      · rw [hd'] at h; cases h
      · cases h
      · cases h
    | opened D =>
      have e : priorityAt R S i =
          (if R.needs i ⊆ D ∧ R.reads i ⊆ S.known then [⟨i, .finish⟩] else []) := by
        simp [priorityAt, hd', hi]
      rw [e]
      by_cases hc : R.needs i ⊆ D ∧ R.reads i ⊆ S.known
      · rw [if_pos hc]
        simp only [List.mem_singleton, Move.mk.injEq]
        constructor
        · rintro ⟨rfl, rfl⟩; exact ⟨rfl, Or.inr ⟨hd', rfl, Or.inl ⟨D, rfl, hc⟩⟩⟩
        · rintro ⟨rfl, h⟩
          rcases h with ⟨h, -⟩ | ⟨-, rfl, -⟩
          · rw [hd'] at h; cases h
          · exact ⟨rfl, rfl⟩
      · rw [if_neg hc]
        simp only [List.not_mem_nil, false_iff, not_and]
        rintro rfl h
        rcases h with ⟨h, -⟩ | ⟨-, -, ⟨D', h, h'⟩ | h⟩
        · rw [hd'] at h; cases h
        · cases h; exact hc h'
        · cases h
    | uncertain D =>
      have e : priorityAt R S i = [] := by simp [priorityAt, hd', hi]
      rw [e]
      simp only [List.not_mem_nil, false_iff, not_and]
      rintro rfl h
      rcases h with ⟨h, -⟩ | ⟨-, -, ⟨D, h, -⟩ | h⟩
      · rw [hd'] at h; cases h
      · cases h
      · cases h
    | completed =>
      have e : priorityAt R S i = [⟨i, .finish⟩] := by simp [priorityAt, hd', hi]
      rw [e]
      simp only [List.mem_singleton, Move.mk.injEq]
      constructor
      · rintro ⟨rfl, rfl⟩; exact ⟨rfl, Or.inr ⟨hd', rfl, Or.inr trivial⟩⟩
      · rintro ⟨rfl, h⟩
        rcases h with ⟨h, -⟩ | ⟨-, rfl, -⟩
        · rw [hd'] at h; cases h
        · exact ⟨rfl, rfl⟩

-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem mem_priority {R : Rules} {S : State} {m : Move} :
    m ∈ priority R S ↔ m.index < R.count ∧ m ∈ priorityAt R S m.index := by
  unfold priority
  rw [List.mem_flatMap]
  constructor
  · rintro ⟨i, hi, hm⟩
    have := (mem_priorityAt.1 hm).1
    subst this
    exact ⟨List.mem_range.1 hi, hm⟩
  · rintro ⟨hi, hm⟩
    exact ⟨m.index, List.mem_range.2 hi, hm⟩

-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem mem_ordinaryAt {R : Rules} {S : State} {i : ℕ} {m : Move} :
    m ∈ ordinaryAt R S i ↔ m.index = i ∧ R.derive i = false ∧
      ((m.part = .start ∧ S.inst i = .closed ∧ R.when i ⊆ S.known) ∨
       (∃ e D, m.part = .step e ∧ S.inst i = .opened D ∧ e ∈ R.steps i ∧ stepReady R S i D e)) := by
  rcases m with ⟨j, p⟩
  by_cases hd : R.derive i = true
  · have e : ordinaryAt R S i = [] := by simp [ordinaryAt, hd]
    rw [e]
    simp only [List.not_mem_nil, false_iff, not_and]
    intro _ h; rw [hd] at h; cases h
  · have hd' : R.derive i = false := by simpa using hd
    cases hi : S.inst i with
    | closed =>
      have e : ordinaryAt R S i = (if R.when i ⊆ S.known then [⟨i, .start⟩] else []) := by
        simp [ordinaryAt, hd', hi]
      rw [e]
      by_cases hw : R.when i ⊆ S.known
      · rw [if_pos hw]
        simp only [List.mem_singleton, Move.mk.injEq]
        constructor
        · rintro ⟨rfl, rfl⟩; exact ⟨rfl, hd', Or.inl ⟨rfl, trivial, hw⟩⟩
        · rintro ⟨rfl, -, ⟨rfl, -⟩ | ⟨e, D, -, h, -⟩⟩
          · exact ⟨rfl, rfl⟩
          · cases h
      · rw [if_neg hw]
        simp only [List.not_mem_nil, false_iff, not_and]
        rintro rfl - h
        rcases h with ⟨-, -, h⟩ | ⟨e, D, -, h, -⟩
        · exact hw h
        · cases h
    | opened D =>
      have e : ordinaryAt R S i =
          ((R.steps i).filter (fun e => decide (stepReady R S i D e))).map (fun e => ⟨i, .step e⟩) := by
        simp [ordinaryAt, hd', hi]
      rw [e]
      simp only [List.mem_map, List.mem_filter, decide_eq_true_eq, Move.mk.injEq]
      constructor
      · rintro ⟨e, ⟨he, hr⟩, rfl, rfl⟩
        exact ⟨rfl, hd', Or.inr ⟨e, D, rfl, rfl, he, hr⟩⟩
      · rintro ⟨rfl, -, ⟨-, h, -⟩ | ⟨e, D', rfl, h, he, hr⟩⟩
        · cases h
        · cases h; exact ⟨e, ⟨he, hr⟩, rfl, rfl⟩
    | uncertain D =>
      have e : ordinaryAt R S i = [] := by simp [ordinaryAt, hd', hi]
      rw [e]
      simp only [List.not_mem_nil, false_iff, not_and]
      rintro rfl - h
      rcases h with ⟨-, h, -⟩ | ⟨e, D', -, h, -⟩ <;> cases h
    | completed =>
      have e : ordinaryAt R S i = [] := by simp [ordinaryAt, hd', hi]
      rw [e]
      simp only [List.not_mem_nil, false_iff, not_and]
      rintro rfl - h
      rcases h with ⟨-, h, -⟩ | ⟨e, D', -, h, -⟩ <;> cases h

-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem mem_ordinary {R : Rules} {S : State} {m : Move} :
    m ∈ ordinary R S ↔ m.index < R.count ∧ m ∈ ordinaryAt R S m.index := by
  unfold ordinary
  rw [List.mem_flatMap]
  constructor
  · rintro ⟨i, hi, hm⟩
    have := (mem_ordinaryAt.1 hm).1
    subst this
    exact ⟨List.mem_range.1 hi, hm⟩
  · rintro ⟨hi, hm⟩
    exact ⟨m.index, List.mem_range.2 hi, hm⟩

-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem mem_enabled {R : Rules} {S : State} {m : Move} :
    m ∈ enabled R S ↔ m ∈ priority R S ∨ (priority R S = [] ∧ m ∈ ordinary R S) := by
  unfold enabled
  split
  · rename_i h; simp [h]
  · rename_i p hp
    constructor
    · exact Or.inl
    · rintro (h | ⟨h, -⟩)
      · exact h
      · exact absurd h hp

-- What a move reads of the literals: each must be known for the move to be enabled.
-- am[implements a-jk-pf-separation-1019@2d33ad]
def readsOf (R : Rules) (S : State) (m : Move) : Finset Lit :=
  match m.part with
  | .start => R.when m.index
  | .derive => R.reads m.index
  | .finish => if S.inst m.index = .completed then ∅ else R.reads m.index
  | .step e => R.when m.index ∪ R.beforeLits m.index e ∪
      (match R.reaction m.index e with
       | none => ∅
       | some r => {r.1})

-- Missing evidence licenses nothing: an enabled move's reads are all known.
-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem enabled_reads_known {R : Rules} {S : State} {m : Move} (h : m ∈ enabled R S) :
    readsOf R S m ⊆ S.known := by
  rcases m with ⟨i, p⟩
  rcases mem_enabled.1 h with h | ⟨-, h⟩
  · obtain ⟨-, h⟩ := mem_priority.1 h
    rcases (mem_priorityAt.1 h).2 with ⟨-, hp, hr, -⟩ | ⟨-, hp, ⟨D, e, -, hr⟩ | e⟩
    · simp only at hp; subst hp; exact hr
    · simp only at hp; subst hp; simp [readsOf, e, hr]
    · simp only at hp; subst hp; simp [readsOf, e]
  · obtain ⟨-, h⟩ := mem_ordinary.1 h
    rcases (mem_ordinaryAt.1 h).2.2 with ⟨hp, -, hw⟩ | ⟨e, D, hp, -, -, ⟨-, -, hw, -, hb, hr⟩⟩
    · simp only at hp; subst hp; exact hw
    · simp only at hp; subst hp
      simp only [readsOf]
      refine Finset.union_subset (Finset.union_subset hw hb) ?_
      unfold reactionReady at hr
      split at hr
      · rename_i e'; rw [e']; exact Finset.empty_subset _
      · rename_i r e'; rw [e']; simpa using hr

-- A Finish needs every needed step done, not merely dispatched, unless every world finished it before
-- the readings.
-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem finish_needs_done {R : Rules} {S : State} {i : ℕ} (h : (⟨i, .finish⟩ : Move) ∈ enabled R S) :
    (∃ D, S.inst i = .opened D ∧ R.needs i ⊆ D) ∨ S.inst i = .completed := by
  rcases mem_enabled.1 h with h | ⟨-, h⟩
  · obtain ⟨-, h⟩ := mem_priority.1 h
    rcases (mem_priorityAt.1 h).2 with ⟨-, hp, -⟩ | ⟨-, -, ⟨D, e, hn, -⟩ | e⟩
    · cases hp
    · exact Or.inl ⟨D, e, hn⟩
    · exact Or.inr e
  · obtain ⟨-, h⟩ := mem_ordinary.1 h
    rcases (mem_ordinaryAt.1 h).2.2 with ⟨hp, -⟩ | ⟨e, D, hp, -⟩ <;> cases hp

-- An act in flight is neither done nor taken again.
-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem step_not_inflight {R : Rules} {S : State} {i e : ℕ} (h : (⟨i, .step e⟩ : Move) ∈ enabled R S) :
    (i, e) ∉ S.inflight := by
  rcases mem_enabled.1 h with h | ⟨-, h⟩
  · obtain ⟨-, h⟩ := mem_priority.1 h
    rcases (mem_priorityAt.1 h).2 with ⟨-, hp, -⟩ | ⟨-, hp, -⟩ <;> cases hp
  · obtain ⟨-, h⟩ := mem_ordinary.1 h
    rcases (mem_ordinaryAt.1 h).2.2 with ⟨hp, -⟩ | ⟨e', D, hp, -, -, ⟨-, hf, -⟩⟩
    · cases hp
    · cases hp; exact hf

-- An old receipt satisfies no new check: a Start opens an instance with nothing done.
-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem start_fresh (R : Rules) (S : State) (i : ℕ) : (step R S ⟨i, .start⟩).inst i = .opened ∅ := by
  simp [step]

-- An investigator's answer replaces the snapshot's reading of its signal and touches no other.
-- am[implements a-jk-pf-separation-1019@2d33ad]
theorem observing_known (S : State) (s : ℕ) (v : Bool) (l : Lit) :
    l ∈ (observing S s v).known ↔ l = (s, v) ∨ (l ∈ S.known ∧ l.1 ≠ s) := by
  simp [observing, written, write1]

/-! ## Worlds

planning_oracle's worlds: a world holds no uncertain or completed instance, takes Finish and Derive
before anything else, in every order, and lands an act in flight only at rest. -/

-- One step a world takes while it settles: a Finish or Derive, or, at rest and while acts land, a landing.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
inductive WStep (R : Rules) (landing : Bool) : State → State → Prop
  | prio {S : State} {m : Move} : m ∈ priority R S → WStep R landing S (step R S m)
  | land {S : State} {a : ℕ × ℕ} : landing = true → priority R S = [] → a ∈ S.inflight →
      WStep R landing S (land R S a)

-- planning_oracle.fixpoints' runs: every state a world passes through while it settles.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Closure (R : Rules) (landing : Bool) : State → State → Prop := Relation.ReflTransGen (WStep R landing)

-- No Finish or Derive is enabled: Model.settled, where a world rests.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def Rest (R : Rules) (S : State) : Prop := priority R S = []

-- am[implements a-jk-pf-lean-model-1019@bf3074]
instance (R : Rules) (S : State) : Decidable (Rest R S) := inferInstanceAs (Decidable (priority R S = []))

-- A world before the readings: any functional valuation, observed signals included, since what each held
-- while the journal's receipts landed is unknown (c-jk-pc-all-valuation-worlds-1019), with the journal's
-- open instances and acts in flight.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
structure Completion (S0 W : State) : Prop where
  functional : Functional W.known
  inst : ∀ i, W.inst i = match S0.inst i with
    | .opened D => .opened D
    | _ => .closed
  inflight : W.inflight = S0.inflight

-- planning_oracle.open_worlds: a completion settled with no act landing, at rest and consistent with
-- every checked reading, since a reading observes the settled world before any act in flight lands.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
def OpenWorld (R : Rules) (S0 X : State) : Prop :=
  ∃ W, Completion S0 W ∧ Closure R false W X ∧ Rest R X ∧ S0.known ⊆ X.known

-- What a classification of the journal's instances must bear out: an instance it completes is open in
-- the journal and closed in every admitted rest, one it keeps is open in every admitted rest, and every
-- admitted rest holds what it entails.
-- am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
structure Observation.Sound (R : Rules) (S0 : State) (o : Observation) : Prop where
  completes : ∀ i, o.completes i = true →
    (∃ D, S0.inst i = .opened D) ∧ ∀ X, OpenWorld R S0 X → X.inst i = .closed
  keeps : ∀ i X, o.keeps i = true → OpenWorld R S0 X → X.inst i ≠ .closed
  entailed : ∀ X, OpenWorld R S0 X → o.entailed ⊆ X.known

-- The exact classification (a-jk-pc-r3-exact-amend-1019): completed where every admitted rest closed an
-- instance the journal has open, kept open where none did, and each Achieves literal of a completed
-- instance that every admitted rest holds entailed. It quantifies over every admitted rest, so it is
-- defined here and computed by planning_oracle.observe; with no admitted rest C1 refuses the snapshot.
-- am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
noncomputable def exactObservation (R : Rules) (S0 : State) : Observation := by
  classical
  exact
    { completes := fun i => decide ((∃ D, S0.inst i = .opened D) ∧ ∀ X, OpenWorld R S0 X → X.inst i = .closed)
      keeps := fun i => decide (∀ X, OpenWorld R S0 X → X.inst i ≠ .closed)
      entailed := ((Finset.range R.count).biUnion (fun i =>
          if (∃ D, S0.inst i = .opened D) ∧ ∀ X, OpenWorld R S0 X → X.inst i = .closed
          then (R.achieves i).toFinset else ∅)).filter (fun l => ∀ X, OpenWorld R S0 X → l ∈ X.known) }

-- am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
theorem exactObservation_sound (R : Rules) (S0 : State) : (exactObservation R S0).Sound R S0 := by
  classical
  refine { completes := fun i h => ?_, keeps := fun i X h hX => ?_, entailed := fun X hX l hl => ?_ }
  · simpa [exactObservation] using h
  · simp only [exactObservation, decide_eq_true_eq] at h
    exact h X hX
  · simp only [exactObservation, Finset.mem_filter] at hl
    exact hl.2 X hX

-- planning_oracle.holds_in's worlds at each turn of a plan's ordinary moves `ms`: an open world's rest
-- states with acts landing, and after each move every rest state the world settles to.
-- am[implements a-jk-pf-lean-model-1019@bf3074]
inductive WorldAt (R : Rules) (S0 : State) (ms : List Move) : ℕ → State → Prop
  | zero {X0 Y : State} : OpenWorld R S0 X0 → Closure R true X0 Y → Rest R Y → WorldAt R S0 ms 0 Y
  | succ {k : ℕ} {X Y : State} (h : k < ms.length) : WorldAt R S0 ms k X →
      Closure R true (step R X ms[k]) Y → Rest R Y → WorldAt R S0 ms (k + 1) Y

/-! ## The K0 invariant

c-jk-pc-invariant-1019: what the model's state guarantees about every world state, X0 the rest state the
readings observed. In a settled model state every move a world can take is either a maybe item the
settle already accounted for or a priority move the model enables, so each world run traces a run of
the model's own priority moves. -/

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
structure Inv (R : Rules) (M X X0 : State) : Prop where
  known : M.known ⊆ X.known
  certain : ∀ i D, M.inst i = .opened D →
    ∃ D', X.inst i = .opened D' ∧ D ⊆ D' ∧ D' ⊆ D ∪ M.dispatched i
  worldOpen : ∀ i D', X.inst i = .opened D' →
    (∃ D, M.inst i = .opened D) ∨ (∃ u, M.inst i = .uncertain u ∧ u ⊆ D' ∧ D' ⊆ u ∪ M.dispatched i)
  world : ∀ i, X.inst i = .closed ∨ ∃ D, X.inst i = .opened D
  inflight : X.inflight ⊆ M.inflight
  unchanged : ∀ s v, s ∉ M.changed → ((s, v) ∈ X.known ↔ (s, v) ∈ X0.known)
  functional : Functional X.known
  rest0 : Rest R X0

-- planning_oracle.embedded: the model's knowledge holds in the world, each certain instance is open there
-- with its done steps, perhaps plus acts in flight that landed, and each instance open there is certain or
-- uncertain and agrees.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
def Embedded (M X : State) : Prop :=
  M.known ⊆ X.known ∧
  (∀ i D, M.inst i = .opened D → ∃ D', X.inst i = .opened D' ∧ D ⊆ D' ∧ D' ⊆ D ∪ M.dispatched i) ∧
  (∀ i D', X.inst i = .opened D' →
    (∃ D, M.inst i = .opened D) ∨ (∃ u, M.inst i = .uncertain u ∧ u ⊆ D' ∧ D' ⊆ u ∪ M.dispatched i))

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem Inv.embedded {R : Rules} {M X X0 : State} (h : Inv R M X X0) : Embedded M X :=
  ⟨h.known, h.certain, h.worldOpen⟩

-- In a settled state each maybe item's write is known, or its opposite forgotten with its signal moved,
-- or the item is unmoved and the signal too.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem Stable.write {R : Rules} {S : State} (h : Stable R S) {i : ℕ} (hi : i < R.count) {mv : Bool}
    (hit : item R S i = some mv) {w : Lit} (hw : w ∈ R.achieves i) :
    w ∈ S.known ∨ (mv = false ∧ w.1 ∉ S.changed) ∨ (neg w ∉ S.known ∧ w.1 ∈ S.changed) := by
  by_cases hk : w ∈ S.known
  · exact Or.inl hk
  · by_cases hm : mv = true ∨ w.1 ∈ S.changed
    · exact Or.inr (Or.inr (h.1 w (hits_mem.2 (Or.inl ⟨i, hi, mem_itemHits.2 ⟨mv, hit, hw, hk, hm⟩⟩))))
    · refine Or.inr (Or.inl ⟨?_, fun hc => hm (Or.inr hc)⟩)
      cases mv
      · rfl
      · exact absurd (Or.inl rfl) hm

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem Stable.act {R : Rules} {S : State} (h : Stable R S) {a : ℕ × ℕ} (ha : a ∈ S.inflight) {r : Lit × Lit}
    (hr : R.reaction a.1 a.2 = some r) : r.2 ∈ S.known ∨ (neg r.2 ∉ S.known ∧ r.2.1 ∈ S.changed) := by
  by_cases hk : r.2 ∈ S.known
  · exact Or.inl hk
  · exact Or.inr (h.1 r.2 (hits_mem.2 (Or.inr ⟨a, ha, mem_actHits.2 ⟨r, hr, rfl, hk⟩⟩)))

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem Stable.not_moves {R : Rules} {S : State} (h : Stable R S) {i : ℕ} (hi : i < R.count) :
    movesB R S i = false :=
  h.2 i (Finset.mem_range.2 hi)

-- A world write each of whose literals the model knows, or has forgotten the opposite of on a moved
-- signal, or the world already holds on an unmoved signal, keeps the invariant.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem Inv.write_world {R : Rules} {M X X0 : State} (hI : Inv R M X X0) {L : List Lit}
    (hL : ∀ w ∈ L, w ∈ M.known ∨ (neg w ∉ M.known ∧ w.1 ∈ M.changed) ∨ (w ∈ X.known ∧ w.1 ∉ M.changed)) :
    Inv R M (write X L) X0 := by
  refine { known := fun l hl => ?_, certain := hI.certain, worldOpen := hI.worldOpen, world := hI.world,
           inflight := hI.inflight, unchanged := fun s v hs => ?_,
           functional := functional_written hI.functional L, rest0 := hI.rest0 }
  · apply mem_written_keep (hI.known hl)
    intro w hw e
    rcases hL w hw with hk | ⟨hn, -⟩ | ⟨hx, -⟩
    · exact hI.functional.eq (hI.known hk) (hI.known hl) e
    · rcases eq_or_neg e with h | h
      · exact h
      · exfalso; apply hn; rw [h, neg_neg]; exact hl
    · exact hI.functional.eq hx (hI.known hl) e
  · show (s, v) ∈ written X.known L ↔ _
    rw [written_value hI.functional s v (fun w hw e => ?_)]
    · exact hI.unchanged s v hs
    · rcases hL w hw with hk | ⟨-, hc⟩ | ⟨hx, -⟩
      · exact hI.known hk
      · exact absurd (e ▸ hc) hs
      · exact hx

-- Every literal of a procedure the world fires possibly holds in the model.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem Inv.possibly {R : Rules} {M X X0 : State} (hI : Inv R M X X0) {L : Finset Lit} (h : L ⊆ X.known) :
    possibly M.known L :=
  fun _ hl hn => hI.functional.not_neg (h hl) (hI.known hn)

-- A Derive a world fires that the model does not enable is one of its maybe items: settled, the model
-- has forgotten whatever it overwrites, or, unmoved, it already fired where the readings were taken.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_absorb_derive {R : Rules} {M X X0 : State} (hS : Stable R M) (hI : Inv R M X X0) {q : ℕ}
    (hX : (⟨q, .derive⟩ : Move) ∈ priority R X) (hM : (⟨q, .derive⟩ : Move) ∉ priority R M) :
    Inv R M (step R X ⟨q, .derive⟩) X0 := by
  obtain ⟨hq, hX⟩ := mem_priority.1 hX
  rcases (mem_priorityAt.1 hX).2 with ⟨hd, -, hr, ha⟩ | ⟨-, hp, -⟩
  swap
  · cases hp
  have hnr : ¬ R.reads q ⊆ M.known := by
    intro hr'
    apply hM
    refine mem_priority.2 ⟨hq, mem_priorityAt.2 ⟨rfl, Or.inl ⟨hd, rfl, hr', fun ha' => ha ?_⟩⟩⟩
    exact ha'.trans hI.known
  have hit : item R M q = some (decide (∃ l ∈ R.reads q, l.1 ∈ M.changed)) := by
    simp [item, hI.possibly hr, hd, hnr]
  show Inv R M (write X (R.achieves q)) X0
  apply hI.write_world
  intro w hw
  rcases hS.write hq hit hw with h | ⟨hm, hc⟩ | h
  · exact Or.inl h
  · refine Or.inr (Or.inr ⟨?_, hc⟩)
    have hunm : ∀ l ∈ R.reads q, l.1 ∉ M.changed := by
      intro l hl hlc
      simp only [decide_eq_false_iff_not, not_exists, not_and] at hm
      exact hm l hl hlc
    have hr0 : R.reads q ⊆ X0.known := by
      intro l hl
      have := (hI.unchanged l.1 l.2 (hunm l hl)).1 (by simpa using hr hl)
      simpa using this
    have ha0 : (R.achieves q).toFinset ⊆ X0.known := by
      by_contra hna
      have : (⟨q, .derive⟩ : Move) ∈ priority R X0 :=
        mem_priority.2 ⟨hq, mem_priorityAt.2 ⟨rfl, Or.inl ⟨hd, rfl, hr0, hna⟩⟩⟩
      rw [hI.rest0] at this
      simp at this
    have hw0 : w ∈ X0.known := ha0 (List.mem_toFinset.2 hw)
    have := (hI.unchanged w.1 w.2 hc).2 (by simpa using hw0)
    simpa using this
  · exact Or.inr (Or.inl h)

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem update_closed_ne {f : ℕ → Inst} {i j : ℕ} (h : j ≠ i) (v : Inst) :
    Function.update f i v j = f j := Function.update_of_ne h v f

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem dispatched_filter (S : State) {i j : ℕ} (h : j ≠ i) :
    ({ S with inflight := S.inflight.filter (·.1 ≠ i) } : State).dispatched j = S.dispatched j := by
  ext e
  simp only [mem_dispatched, Finset.mem_filter]
  constructor
  · exact fun h' => h'.1
  · exact fun h' => ⟨h', h⟩

-- A world closing an instance the model holds uncertain: the model's settle weakens by its Finish.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_absorb_finish {R : Rules} {M X X0 : State} (hS : Stable R M) (hI : Inv R M X X0) {i : ℕ}
    {u : Finset ℕ} (hX : (⟨i, .finish⟩ : Move) ∈ priority R X) (hMu : M.inst i = .uncertain u) :
    Inv R M (step R X ⟨i, .finish⟩) X0 := by
  obtain ⟨hi, hX⟩ := mem_priority.1 hX
  rcases (mem_priorityAt.1 hX).2 with ⟨-, hp, -⟩ | ⟨hd, -, ⟨D', hXi, hn, hr⟩ | hXi⟩
  · cases hp
  · have hit : item R M i = some true := by simp [item, hI.possibly hr, hd, hMu]
    have hW : Inv R M (write X (R.achieves i)) X0 := by
      apply hI.write_world
      intro w hw
      rcases hS.write hi hit hw with h | ⟨h, -⟩ | h
      · exact Or.inl h
      · cases h
      · exact Or.inr (Or.inl h)
    have hstep : step R X ⟨i, .finish⟩ = { write X (R.achieves i) with
        inst := Function.update X.inst i .closed, inflight := X.inflight.filter (·.1 ≠ i) } := by
      simp [step, hXi]
    rw [hstep]
    refine { known := hW.known, certain := ?_, worldOpen := ?_, world := ?_, inflight := ?_,
             unchanged := hW.unchanged, functional := hW.functional, rest0 := hI.rest0 }
    · intro j D hj
      have hji : j ≠ i := by rintro rfl; rw [hMu] at hj; cases hj
      obtain ⟨D'', h1, h2, h3⟩ := hI.certain j D hj
      exact ⟨D'', by simp only [update_closed_ne hji]; exact h1, h2, h3⟩
    · intro j D'' hj
      have hji : j ≠ i := by rintro rfl; simp at hj
      simp only [update_closed_ne hji] at hj
      exact hI.worldOpen j D'' hj
    · intro j
      by_cases hji : j = i
      · subst hji; left; simp
      · simp only [update_closed_ne hji]; exact hI.world j
    · exact (Finset.filter_subset _ _).trans hI.inflight
  · rcases hI.world i with h | ⟨D, h⟩ <;> rw [hXi] at h <;> cases h

-- A Finish a world fires of an instance the settled model holds certain is enabled in the model: else
-- the settle would have made the instance uncertain.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem finish_certain_enabled {R : Rules} {M X X0 : State} (hS : Stable R M) (hI : Inv R M X X0) {i : ℕ}
    {D : Finset ℕ} (hX : (⟨i, .finish⟩ : Move) ∈ priority R X) (hMi : M.inst i = .opened D) :
    (⟨i, .finish⟩ : Move) ∈ priority R M := by
  obtain ⟨hi, hX⟩ := mem_priority.1 hX
  rcases (mem_priorityAt.1 hX).2 with ⟨-, hp, -⟩ | ⟨hd, -, ⟨D', hXi, hn, hr⟩ | hXi⟩
  · cases hp
  · obtain ⟨D'', hXi', -, hsup⟩ := hI.certain i D hMi
    rw [hXi] at hXi'
    cases hXi'
    by_cases hc : R.needs i ⊆ D ∧ R.reads i ⊆ M.known
    · exact mem_priority.2 ⟨hi, mem_priorityAt.2 ⟨rfl, Or.inr ⟨hd, rfl, Or.inl ⟨D, hMi, hc⟩⟩⟩⟩
    · exfalso
      have hm : movesB R M i = true := by
        simp only [movesB, hMi, hd, decide_eq_true_eq, Bool.not_false, Bool.and_true, Bool.and_eq_true]
        exact ⟨⟨hi, hI.possibly hr⟩, hn.trans hsup, hc⟩
      rw [hS.not_moves hi] at hm
      cases hm
  · rcases hI.world i with h | ⟨D', h⟩ <;> rw [hXi] at h <;> cases h

-- The instance half of a landing: its step done in the world, which the model counted as in flight.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_land_inst {R : Rules} {M X X0 : State} (hI : Inv R M X X0) (ai ae : ℕ)
    (haM : (ai, ae) ∈ M.inflight) : Inv R M (landed X (ai, ae)) X0 := by
  have hdisp : ae ∈ M.dispatched ai := mem_dispatched.2 haM
  have hinf : X.inflight.erase (ai, ae) ⊆ M.inflight := (Finset.erase_subset _ _).trans hI.inflight
  unfold landed
  dsimp only
  cases hx : X.inst ai with
  | opened D0 =>
    refine { known := hI.known, certain := ?_, worldOpen := ?_, world := ?_, inflight := hinf,
             unchanged := hI.unchanged, functional := hI.functional, rest0 := hI.rest0 }
    · intro j D hj
      obtain ⟨D', hx', h1, h2⟩ := hI.certain j D hj
      by_cases e : j = ai
      · subst e
        rw [hx] at hx'
        cases hx'
        exact ⟨insert ae D0, by simp, h1.trans (Finset.subset_insert _ _),
          Finset.insert_subset (Finset.mem_union_right _ hdisp) h2⟩
      · exact ⟨D', by simp only [update_closed_ne e]; exact hx', h1, h2⟩
    · intro j D' hj
      by_cases e : j = ai
      · subst e
        simp only [Function.update_self, Inst.opened.injEq] at hj
        subst hj
        rcases hI.worldOpen j D0 hx with h | ⟨u, hu, h1, h2⟩
        · exact Or.inl h
        · exact Or.inr ⟨u, hu, h1.trans (Finset.subset_insert _ _),
            Finset.insert_subset (Finset.mem_union_right _ hdisp) h2⟩
      · simp only [update_closed_ne e] at hj
        exact hI.worldOpen j D' hj
    · intro j
      by_cases e : j = ai
      · subst e; right; exact ⟨insert ae D0, by simp⟩
      · simp only [update_closed_ne e]; exact hI.world j
  | closed =>
    exact { known := hI.known, certain := hI.certain, worldOpen := hI.worldOpen, world := hI.world,
            inflight := hinf, unchanged := hI.unchanged, functional := hI.functional, rest0 := hI.rest0 }
  | uncertain D0 =>
    exact { known := hI.known, certain := hI.certain, worldOpen := hI.worldOpen, world := hI.world,
            inflight := hinf, unchanged := hI.unchanged, functional := hI.functional, rest0 := hI.rest0 }
  | completed =>
    exact { known := hI.known, certain := hI.certain, worldOpen := hI.worldOpen, world := hI.world,
            inflight := hinf, unchanged := hI.unchanged, functional := hI.functional, rest0 := hI.rest0 }

-- An act in flight landing in a world is one of the settled model's items: its write is known or
-- forgotten, and its step was already counted as possibly done.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_absorb_land {R : Rules} {M X X0 : State} (hS : Stable R M) (hI : Inv R M X X0) {a : ℕ × ℕ}
    (ha : a ∈ X.inflight) : Inv R M (land R X a) X0 := by
  obtain ⟨ai, ae⟩ := a
  have haM := hI.inflight ha
  have hI' := inv_land_inst hI ai ae haM
  unfold land
  dsimp only
  cases hr : R.reaction ai ae with
  | none => exact hI'
  | some r =>
    apply hI'.write_world
    intro w hw
    simp only [List.mem_singleton] at hw
    subst hw
    rcases hS.act haM hr with h | h
    · exact Or.inl h
    · exact Or.inr (Or.inl h)

-- Writing the same literals in the model and the world keeps the invariant.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem Inv.write_both {R : Rules} {M X X0 : State} (hI : Inv R M X X0) (L : List Lit) :
    Inv R (write M L) (write X L) X0 := by
  refine { known := written_mono hI.known L, certain := hI.certain, worldOpen := hI.worldOpen,
           world := hI.world, inflight := hI.inflight, unchanged := fun s v hs => ?_,
           functional := functional_written hI.functional L, rest0 := hI.rest0 }
  have hsL : ∀ w ∈ L, w.1 ≠ (s, v).1 := fun w hw e =>
    hs (Finset.mem_union_right _ (List.mem_toFinset.2 (List.mem_map.2 ⟨w, hw, e⟩)))
  show (s, v) ∈ written X.known L ↔ _
  rw [written_other hsL]
  exact hI.unchanged s v (fun h => hs (Finset.mem_union_left _ h))

-- An instance closed by its Finish, its acts in flight dropped.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
def State.close (S : State) (i : ℕ) : State :=
  { S with inst := Function.update S.inst i .closed, inflight := S.inflight.filter (·.1 ≠ i) }

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
@[simp] theorem close_inst_self (S : State) (i : ℕ) : (S.close i).inst i = .closed := by simp [State.close]

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem close_inst_ne (S : State) {i j : ℕ} (h : j ≠ i) : (S.close i).inst j = S.inst j := by
  simp [State.close, h]

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem close_inflight (S : State) (i : ℕ) : (S.close i).inflight = S.inflight.filter (·.1 ≠ i) := rfl

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem dispatched_close (S : State) {i j : ℕ} (h : j ≠ i) : (S.close i).dispatched j = S.dispatched j := by
  ext e
  simp only [mem_dispatched, close_inflight, Finset.mem_filter]
  exact ⟨fun h' => h'.1, fun h' => ⟨h', h⟩⟩

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem step_finish_open {R : Rules} {S : State} {i : ℕ} {D : Finset ℕ} (h : S.inst i = .opened D) :
    step R S ⟨i, .finish⟩ = (write S (R.achieves i)).close i := by
  simp [step, h, State.close, write]

-- Closing one instance in the model and the world keeps the invariant.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem Inv.close_both {R : Rules} {M X X0 : State} (hI : Inv R M X X0) (i : ℕ) :
    Inv R (M.close i) (X.close i) X0 := by
  refine { known := hI.known, certain := ?_, worldOpen := ?_, world := ?_, inflight := ?_,
           unchanged := hI.unchanged, functional := hI.functional, rest0 := hI.rest0 }
  · intro j D hj
    have hji : j ≠ i := by rintro rfl; rw [close_inst_self] at hj; cases hj
    rw [close_inst_ne M hji] at hj
    obtain ⟨D', h1, h2, h3⟩ := hI.certain j D hj
    exact ⟨D', by rw [close_inst_ne X hji]; exact h1, h2, by rw [dispatched_close M hji]; exact h3⟩
  · intro j D' hj
    have hji : j ≠ i := by rintro rfl; rw [close_inst_self] at hj; cases hj
    rw [close_inst_ne X hji] at hj
    rcases hI.worldOpen j D' hj with ⟨D, h⟩ | ⟨u, h, h1, h2⟩
    · exact Or.inl ⟨D, by rw [close_inst_ne M hji]; exact h⟩
    · exact Or.inr ⟨u, by rw [close_inst_ne M hji]; exact h, h1, by rw [dispatched_close M hji]; exact h2⟩
  · intro j
    by_cases hji : j = i
    · subst hji; exact Or.inl (close_inst_self X j)
    · rw [close_inst_ne X hji]; exact hI.world j
  · intro a ha
    rw [close_inflight] at ha ⊢
    obtain ⟨ha, hai⟩ := Finset.mem_filter.1 ha
    exact Finset.mem_filter.2 ⟨hI.inflight ha, hai⟩

-- A priority move the model enables and the world takes keeps the invariant.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_follow {R : Rules} {M X X0 : State} (hI : Inv R M X X0) {p : Move}
    (hM : p ∈ priority R M) (hX : p ∈ priority R X) : Inv R (step R M p) (step R X p) X0 := by
  rcases p with ⟨i, part⟩
  obtain ⟨-, hMp⟩ := mem_priority.1 hM
  obtain ⟨-, hXp⟩ := mem_priority.1 hX
  rcases (mem_priorityAt.1 hMp).2 with ⟨-, hp, -, -⟩ | ⟨-, hp, ⟨D, hMi, -, -⟩ | hMi⟩
  · simp only at hp; subst hp
    exact hI.write_both (R.achieves i)
  · simp only at hp; subst hp
    obtain ⟨D', hXi, -, -⟩ := hI.certain i D hMi
    rw [step_finish_open hMi, step_finish_open hXi]
    exact (hI.write_both _).close_both i
  · exfalso
    simp only at hp; subst hp
    rcases (mem_priorityAt.1 hXp).2 with ⟨-, hp', -⟩ | ⟨-, -, ⟨D', hXi, -⟩ | hXi⟩
    · cases hp'
    · rcases hI.worldOpen i D' hXi with ⟨D, h⟩ | ⟨u, h, -⟩ <;> rw [hMi] at h <;> cases h
    · rcases hI.world i with h | ⟨D', h⟩ <;> rw [hXi] at h <;> cases h

-- A Derive the model enables that the world, at its reads, does not: the world already holds its writes.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_noop_derive {R : Rules} {M X X0 : State} (hI : Inv R M X X0) {q : ℕ}
    (hM : (⟨q, .derive⟩ : Move) ∈ priority R M) (hX : (⟨q, .derive⟩ : Move) ∉ priority R X) :
    Inv R (step R M ⟨q, .derive⟩) X X0 := by
  obtain ⟨hq, hMp⟩ := mem_priority.1 hM
  rcases (mem_priorityAt.1 hMp).2 with ⟨hd, -, hr, -⟩ | ⟨-, hp, -⟩
  swap
  · cases hp
  have hrX : R.reads q ⊆ X.known := hr.trans hI.known
  have haX : (R.achieves q).toFinset ⊆ X.known := by
    by_contra hna
    exact hX (mem_priority.2 ⟨hq, mem_priorityAt.2 ⟨rfl, Or.inl ⟨hd, rfl, hrX, hna⟩⟩⟩)
  show Inv R (write M (R.achieves q)) X X0
  refine { known := fun l hl => ?_, certain := hI.certain, worldOpen := hI.worldOpen, world := hI.world,
           inflight := hI.inflight,
           unchanged := fun s v hs => hI.unchanged s v (fun h => hs (Finset.mem_union_left _ h)),
           functional := hI.functional, rest0 := hI.rest0 }
  rcases mem_written hl with h | h
  · exact hI.known h
  · exact haX (List.mem_toFinset.2 h)

-- A completed instance's journal-only Finish changes nothing a world holds.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0] am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
theorem inv_noop_completed {R : Rules} {M X X0 : State} (hI : Inv R M X X0) {i : ℕ}
    (hMi : M.inst i = .completed) : Inv R (step R M ⟨i, .finish⟩) X X0 := by
  have e : step R M ⟨i, .finish⟩ = { M with inst := Function.update M.inst i .closed } := by
    simp [step, hMi]
  rw [e]
  refine { known := hI.known, certain := ?_, worldOpen := ?_, world := hI.world, inflight := hI.inflight,
           unchanged := hI.unchanged, functional := hI.functional, rest0 := hI.rest0 }
  · intro j D hj
    have hji : j ≠ i := by rintro rfl; simp at hj
    simp only [update_closed_ne hji] at hj
    exact hI.certain j D hj
  · intro j D' hj
    rcases hI.worldOpen j D' hj with ⟨D, h⟩ | ⟨u, h, h1, h2⟩
    · have hji : j ≠ i := by rintro rfl; rw [hMi] at h; cases h
      exact Or.inl ⟨D, by simp only [update_closed_ne hji]; exact h⟩
    · have hji : j ≠ i := by rintro rfl; rw [hMi] at h; cases h
      exact Or.inr ⟨u, by simp only [update_closed_ne hji]; exact h, h1, h2⟩

-- A Finish the model enables of an instance it holds open is enabled in every world it embeds.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem finish_enabled_world {R : Rules} {M X X0 : State} (hI : Inv R M X X0) {i : ℕ} {D : Finset ℕ}
    (hM : (⟨i, .finish⟩ : Move) ∈ priority R M) (hMi : M.inst i = .opened D) :
    (⟨i, .finish⟩ : Move) ∈ priority R X := by
  obtain ⟨hi, hMp⟩ := mem_priority.1 hM
  rcases (mem_priorityAt.1 hMp).2 with ⟨-, hp, -⟩ | ⟨hd, -, ⟨D1, hMi1, hn, hr⟩ | hMi1⟩
  · cases hp
  · rw [hMi] at hMi1
    cases hMi1
    obtain ⟨D', hXi, h1, -⟩ := hI.certain i D hMi
    exact mem_priority.2 ⟨hi, mem_priorityAt.2 ⟨rfl, Or.inr ⟨hd, rfl,
      Or.inl ⟨D', hXi, hn.trans h1, hr.trans hI.known⟩⟩⟩⟩
  · rw [hMi] at hMi1; cases hMi1

-- The settle only weakens the model's state: forgetting, making instances uncertain, moving signals.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_round {R : Rules} {S X X0 : State} (hI : Inv R S X X0) : Inv R (round R S) X X0 := by
  refine { known := (round_known_subset R S).trans hI.known, certain := ?_, worldOpen := ?_,
           world := hI.world, inflight := hI.inflight,
           unchanged := fun s v hs => hI.unchanged s v (fun h => hs (round_changed_superset R S h)),
           functional := hI.functional, rest0 := hI.rest0 }
  · intro j D hj
    rcases round_inst R S j with e | ⟨D', -, e⟩
    · rw [e] at hj; exact hI.certain j D hj
    · rw [e] at hj; cases hj
  · intro j D' hj
    rcases hI.worldOpen j D' hj with ⟨D, h⟩ | ⟨u, h, h1, h2⟩
    · rcases round_inst R S j with e | ⟨E, eS, e⟩
      · exact Or.inl ⟨D, e.trans h⟩
      · rw [eS] at h
        cases h
        obtain ⟨D'', hx, e1, e2⟩ := hI.certain j D eS
        rw [hj] at hx
        cases hx
        exact Or.inr ⟨D, e, e1, e2⟩
    · rcases round_inst R S j with e | ⟨E, eS, e⟩
      · exact Or.inr ⟨u, e.trans h, h1, h2⟩
      · rw [eS] at h; cases h

-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_settle {R : Rules} {S X X0 : State} (hI : Inv R S X X0) : Inv R (settle R S) X X0 :=
  settleFuel_props R (fun S T => Inv R S X X0 → Inv R T X X0) (fun _ h => h)
    (fun _ _ h hS => h (inv_round hS)) _ S hI

-- An ordinary move the model enables at rest is enabled in every world at rest it embeds, and taking it in
-- both keeps the invariant.
-- am[implements a-jk-pf-k0-invariant-1019@54acf0]
theorem inv_ordinary {R : Rules} {M X X0 : State} (hI : Inv R M X X0) (hMr : Rest R M) (hXr : Rest R X)
    {m : Move} (hm : m ∈ enabled R M) : m ∈ enabled R X ∧ Inv R (step R M m) (step R X m) X0 := by
  have hord : m ∈ ordinary R M := by
    rcases mem_enabled.1 hm with h | ⟨-, h⟩
    · unfold Rest at hMr; rw [hMr] at h; simp at h
    · exact h
  rcases m with ⟨i, part⟩
  obtain ⟨hi, hO⟩ := mem_ordinary.1 hord
  obtain ⟨-, hd, ⟨hp, hMi, hw⟩ | ⟨e, D, hp, hMi, he, hr⟩⟩ := mem_ordinaryAt.1 hO
  · simp only at hp; subst hp
    have hXi : X.inst i = .closed := by
      rcases hI.world i with h | ⟨D', h⟩
      · exact h
      · rcases hI.worldOpen i D' h with ⟨D, h'⟩ | ⟨u, h', -⟩ <;> rw [hMi] at h' <;> cases h'
    refine ⟨mem_enabled.2 (Or.inr ⟨hXr, mem_ordinary.2 ⟨hi, mem_ordinaryAt.2
      ⟨rfl, hd, Or.inl ⟨rfl, hXi, hw.trans hI.known⟩⟩⟩⟩), ?_⟩
    show Inv R { M with inst := Function.update M.inst i (.opened ∅) }
      { X with inst := Function.update X.inst i (.opened ∅) } X0
    refine { known := hI.known, certain := ?_, worldOpen := ?_, world := ?_, inflight := hI.inflight,
             unchanged := hI.unchanged, functional := hI.functional, rest0 := hI.rest0 }
    · intro j E hj
      by_cases ej : j = i
      · subst ej
        simp only [Function.update_self, Inst.opened.injEq] at hj
        subst hj
        exact ⟨∅, by simp, Finset.Subset.refl _, Finset.empty_subset _⟩
      · simp only [update_closed_ne ej] at hj ⊢
        exact hI.certain j E hj
    · intro j E hj
      by_cases ej : j = i
      · subst ej; exact Or.inl ⟨∅, by simp⟩
      · simp only [update_closed_ne ej] at hj ⊢
        exact hI.worldOpen j E hj
    · intro j
      by_cases ej : j = i
      · subst ej; exact Or.inr ⟨∅, by simp⟩
      · simp only [update_closed_ne ej]; exact hI.world j
  · simp only at hp; subst hp
    obtain ⟨heD, hef, hw, hb, hbl, hrr⟩ := hr
    obtain ⟨D', hXi, h1, h2⟩ := hI.certain i D hMi
    have heD' : e ∉ D' := by
      intro h
      rcases Finset.mem_union.1 (h2 h) with h | h
      · exact heD h
      · exact hef (mem_dispatched.1 h)
    have hrrX : reactionReady R X i e = true := by
      unfold reactionReady at hrr ⊢
      cases hre : R.reaction i e with
      | none => rfl
      | some r =>
        rw [hre] at hrr
        simp only [decide_eq_true_eq] at hrr ⊢
        exact hI.known hrr
    have hXr' : stepReady R X i D' e :=
      ⟨heD', fun h => hef (hI.inflight h), hw.trans hI.known, hb.trans h1, hbl.trans hI.known, hrrX⟩
    refine ⟨mem_enabled.2 (Or.inr ⟨hXr, mem_ordinary.2 ⟨hi, mem_ordinaryAt.2
      ⟨rfl, hd, Or.inr ⟨e, D', rfl, hXi, he, hXr'⟩⟩⟩⟩), ?_⟩
    have hM' : Inv R { M with inst := Function.update M.inst i (.opened (insert e D)) }
        { X with inst := Function.update X.inst i (.opened (insert e D')) } X0 := by
      refine { known := hI.known, certain := ?_, worldOpen := ?_, world := ?_, inflight := hI.inflight,
               unchanged := hI.unchanged, functional := hI.functional, rest0 := hI.rest0 }
      · intro j E hj
        by_cases ej : j = i
        · subst ej
          simp only [Function.update_self, Inst.opened.injEq] at hj
          subst hj
          refine ⟨insert e D', by simp, Finset.insert_subset_insert _ h1, ?_⟩
          intro x hx
          rcases Finset.mem_insert.1 hx with rfl | hx
          · exact Finset.mem_union_left _ (Finset.mem_insert_self _ _)
          · rcases Finset.mem_union.1 (h2 hx) with h | h
            · exact Finset.mem_union_left _ (Finset.mem_insert_of_mem h)
            · exact Finset.mem_union_right _ h
        · simp only [update_closed_ne ej] at hj ⊢
          exact hI.certain j E hj
      · intro j E hj
        by_cases ej : j = i
        · subst ej; exact Or.inl ⟨insert e D, by simp⟩
        · simp only [update_closed_ne ej] at hj ⊢
          exact hI.worldOpen j E hj
      · intro j
        by_cases ej : j = i
        · subst ej; exact Or.inr ⟨insert e D', by simp⟩
        · simp only [update_closed_ne ej]; exact hI.world j
    have eM : step R M ⟨i, .step e⟩ = (match R.reaction i e with
        | none => { M with inst := Function.update M.inst i (.opened (insert e D)) }
        | some r => write { M with inst := Function.update M.inst i (.opened (insert e D)) } [r.2]) := by
      simp [step, hMi, Inst.done]
    have eX : step R X ⟨i, .step e⟩ = (match R.reaction i e with
        | none => { X with inst := Function.update X.inst i (.opened (insert e D')) }
        | some r => write { X with inst := Function.update X.inst i (.opened (insert e D')) } [r.2]) := by
      simp [step, hXi, Inst.done]
    rw [eM, eX]
    cases R.reaction i e with
    | none => exact hM'
    | some r => exact hM'.write_both [r.2]

/-! ## Plan soundness -/

-- The model's own priority moves, each followed by the settle (planning_oracle's apply).
-- am[implements a-jk-pf-plan-holds-closure-1019@2f78f9]
def MStep (R : Rules) (M M' : State) : Prop := ∃ p ∈ priority R M, M' = settle R (step R M p)

-- R1 (a-jk-pc-r1-closure-1019): from M0 the model's priority moves reach Mend, which rests; every run of
-- them is finite; and every run that rests, rests in Mend.
-- am[implements a-jk-pc-r1-closure-1019@f9b888]
structure Determined (R : Rules) (M0 Mend : State) : Prop where
  reach : Relation.ReflTransGen (MStep R) M0 Mend
  rest : Rest R Mend
  finite : ∀ M, Relation.ReflTransGen (MStep R) M0 M → Acc (fun a b => MStep R b a) M
  unique : ∀ M, Relation.ReflTransGen (MStep R) M0 M → Rest R M → M = Mend

-- A world at rest: the model's remaining priority moves are Derives the world already made and journal-only
-- Finishes, so the run they make ends in the closure's one rest state, which embeds the world.
theorem track_rest {R : Rules} {M0 Mend Y X0 : State} (hD : Determined R M0 Mend) (hY : Rest R Y) :
    ∀ M, Acc (fun a b => MStep R b a) M → Relation.ReflTransGen (MStep R) M0 M → Stable R M →
      Inv R M Y X0 → Inv R Mend Y X0 := by
  intro M hacc
  induction hacc with
  | intro M _ ih =>
    intro hM hS hI
    by_cases hr : Rest R M
    · rw [← hD.unique M hM hr]; exact hI
    · obtain ⟨p, hp⟩ : ∃ p, p ∈ priority R M := List.exists_mem_of_ne_nil _ hr
      have hstep : Inv R (step R M p) Y X0 := by
        rcases p with ⟨i, part⟩
        obtain ⟨-, hMp⟩ := mem_priority.1 hp
        rcases (mem_priorityAt.1 hMp).2 with ⟨-, hpart, -, -⟩ | ⟨-, hpart, ⟨D, hMi, -, -⟩ | hMi⟩
        · simp only at hpart; subst hpart
          refine inv_noop_derive hI hp ?_
          unfold Rest at hY; rw [hY]; simp
        · simp only at hpart; subst hpart
          have := finish_enabled_world hI hp hMi
          unfold Rest at hY; rw [hY] at this; simp at this
        · simp only at hpart; subst hpart
          exact inv_noop_completed hI hMi
      have hM' : MStep R M (settle R (step R M p)) := ⟨p, hp, rfl⟩
      exact ih _ hM' (hM.tail hM') (settle_stable R _) (inv_settle hstep)

-- Every rest state a world settles to from a state the model's closure-root run embeds is embedded by the
-- closure's one rest state: each world move is a maybe item of the current model state or a move it
-- enables, and once the world rests the model's remaining moves pass as moves it already made.
-- am[implements a-jk-pf-plan-holds-closure-1019@2f78f9]
theorem track {R : Rules} {M0 Mend X0 : State} (hD : Determined R M0 Mend) {X Y : State}
    (hc : Closure R true X Y) (hY : Rest R Y) :
    ∀ {M : State}, Relation.ReflTransGen (MStep R) M0 M → Stable R M → Inv R M X X0 → Inv R Mend Y X0 := by
  induction hc using Relation.ReflTransGen.head_induction_on with
  | refl =>
    intro M hM hS hI
    exact track_rest hD hY M (hD.finite M hM) hM hS hI
  | @head X X1 hw _ ih =>
    intro M hM hS hI
    cases hw with
    | @prio p hp =>
      by_cases hpM : p ∈ priority R M
      · have hM' : MStep R M (settle R (step R M p)) := ⟨p, hpM, rfl⟩
        exact ih (hM.tail hM') (settle_stable R _) (inv_settle (inv_follow hI hpM hp))
      · apply ih hM hS
        rcases p with ⟨i, part⟩
        obtain ⟨-, hXp⟩ := mem_priority.1 hp
        rcases (mem_priorityAt.1 hXp).2 with ⟨-, hpart, -, -⟩ | ⟨-, hpart, ⟨D', hXi, -, -⟩ | hXi⟩
        · simp only at hpart; subst hpart
          exact inv_absorb_derive hS hI hp hpM
        · simp only at hpart; subst hpart
          rcases hI.worldOpen i D' hXi with ⟨D, hMi⟩ | ⟨u, hMi, -, -⟩
          · exact absurd (finish_certain_enabled hS hI hp hMi) hpM
          · exact inv_absorb_finish hS hI hp hMi
        · exfalso
          rcases hI.world i with h | ⟨D', h⟩ <;> rw [hXi] at h <;> cases h
    | @land a _ _ ha =>
      exact ih hM hS (inv_absorb_land hS hI ha)

-- The world's settling before the readings, with no act landing: only a Finish changes an instance,
-- closing it with its needed steps done as the journal recorded them and dropping its acts in flight.
theorem initial_closure {R : Rules} {S0 W : State} (hW : Completion S0 W) {X : State}
    (hc : Closure R false W X) :
    Functional X.known ∧ X.inflight ⊆ W.inflight ∧
    ∀ i, X.inst i = W.inst i ∨
      (X.inst i = .closed ∧ (∃ D, W.inst i = .opened D ∧ i < R.count ∧ R.derive i = false ∧ R.needs i ⊆ D) ∧
        ∀ a ∈ X.inflight, a.1 ≠ i) := by
  induction hc with
  | refl => exact ⟨hW.functional, Finset.Subset.refl _, fun i => Or.inl rfl⟩
  | @tail Y Z _ hw ih =>
    obtain ⟨hf, hinf, hinst⟩ := ih
    cases hw with
    | @land a hl _ _ => cases hl
    | @prio p hp =>
      rcases p with ⟨i, part⟩
      obtain ⟨hi, hYp⟩ := mem_priority.1 hp
      rcases (mem_priorityAt.1 hYp).2 with ⟨-, hpart, -, -⟩ | ⟨hd, hpart, ⟨D, hYi, hn, -⟩ | hYi⟩
      · simp only at hpart; subst hpart
        exact ⟨functional_written hf _, hinf, hinst⟩
      · simp only at hpart; subst hpart
        rw [step_finish_open hYi]
        refine ⟨functional_written hf _, fun a ha => hinf (Finset.mem_filter.1 ha).1, fun j => ?_⟩
        by_cases hji : j = i
        · subst hji
          right
          refine ⟨close_inst_self _ _, ?_, fun a ha => (Finset.mem_filter.1 ha).2⟩
          rcases hinst j with h | ⟨h, -⟩
          · exact ⟨D, h.symm.trans hYi, hi, hd, hn⟩
          · rw [hYi] at h; cases h
        · rw [close_inst_ne _ hji]
          rcases hinst j with h | ⟨h1, h2, h3⟩
          · exact Or.inl h
          · exact Or.inr ⟨h1, h2, fun a ha => h3 a (Finset.mem_filter.1 ha).1⟩
      · exfalso
        rcases hinst i with h | ⟨h, -⟩
        · have hWi := hW.inst i
          rw [← h, hYi] at hWi
          cases hS : S0.inst i <;> simp [hS] at hWi
        · rw [hYi] at h; cases h

-- At the readings an observed snapshot embeds every admitted world, under any classification the admitted
-- rests bear out: an instance it completes is closed there, one it keeps is open there as the journal
-- says, every other open one is open there with the journal's done steps or closed, and the world holds
-- every literal read or entailed (R3's discharge, a-jk-pc-r3-exact-amend-1019).
-- am[implements a-jk-pf-plan-holds-closure-1019@2f78f9] am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
theorem inv_start {R : Rules} {S0 X0 : State} {o : Observation} (ho : o.Sound R S0)
    (hX : OpenWorld R S0 X0) : Inv R (observeWith S0 o) X0 X0 := by
  obtain ⟨W, hW, hc, hrest, hk⟩ := id hX
  obtain ⟨hf, hinf, hinst⟩ := initial_closure hW hc
  have hWopen : ∀ i D, S0.inst i = .opened D → W.inst i = .opened D := by
    intro i D h; rw [hW.inst i, h]
  -- An instance the journal has open is open in X0 with the journal's done steps, or the world's Finish
  -- closed it and dropped its acts in flight.
  have hopen : ∀ i D, S0.inst i = .opened D →
      X0.inst i = .opened D ∨ (X0.inst i = .closed ∧ ∀ a ∈ X0.inflight, a.1 ≠ i) := by
    intro i D h
    rcases hinst i with e | ⟨e1, -, e3⟩
    · exact Or.inl (e.trans (hWopen i D h))
    · exact Or.inr ⟨e1, e3⟩
  have hobs : ∀ i D, S0.inst i = .opened D → (observeWith S0 o).inst i =
      if o.completes i then .completed else if o.keeps i then .opened D else .uncertain D := by
    intro i D h; simp [observeWith, h]
  refine { known := fun l hl => ?_, certain := ?_, worldOpen := ?_, world := ?_, inflight := ?_,
           unchanged := fun _ _ _ => Iff.rfl, functional := hf, rest0 := hrest }
  · rcases Finset.mem_union.1 hl with h | h
    · exact hk h
    · exact ho.entailed X0 hX h
  · intro i D hi
    obtain ⟨D0, hS⟩ : ∃ D0, S0.inst i = .opened D0 := by
      cases hS : S0.inst i with
      | opened D0 => exact ⟨D0, rfl⟩
      | _ => simp [observeWith, hS] at hi
    rw [hobs i D0 hS] at hi
    split_ifs at hi with h1 h2
    cases hi
    rcases hopen i D hS with e | ⟨e, -⟩
    · exact ⟨D, e, Finset.Subset.refl _, Finset.subset_union_left⟩
    · exact absurd e (ho.keeps i X0 h2 hX)
  · intro i D' hi
    have hWi : W.inst i = .opened D' := by
      rcases hinst i with h | ⟨h, -⟩
      · exact h.symm.trans hi
      · rw [hi] at h; cases h
    have hS : S0.inst i = .opened D' := by
      have := hW.inst i
      rw [hWi] at this
      cases hS : S0.inst i <;> rw [hS] at this <;> simp at this
      · rw [this]
    rw [hobs i D' hS]
    split_ifs with h1 h2
    · exfalso
      rw [(ho.completes i h1).2 X0 hX] at hi
      cases hi
    · left
      exact ⟨D', rfl⟩
    · right
      exact ⟨D', rfl, Finset.Subset.refl _, Finset.subset_union_left⟩
  · intro i
    rcases hinst i with h | ⟨h, -⟩
    · rw [h, hW.inst i]
      cases S0.inst i <;> simp
    · exact Or.inl h
  · intro a ha
    refine Finset.mem_filter.2 ⟨hW.inflight ▸ hinf ha, ?_⟩
    cases hc' : o.completes a.1
    · rfl
    · obtain ⟨⟨D, hS⟩, hclosed⟩ := ho.completes a.1 hc'
      rcases hopen a.1 D hS with e | ⟨-, e3⟩
      · rw [hclosed X0 hX] at e
        cases e
      · exact absurd rfl (e3 a ha)

/-! ## The plan theorem -/

-- A plan the repaired planner accepts, by its ordinary moves and the model's state at each turn: the start
-- settled from the snapshot observed under a classification the admitted rests bear out (R3), each
-- ordinary move enabled at its turn, each closure determined (R1), and the goal known at the end.
-- am[implements a-jk-pf-plan-holds-closure-1019@2f78f9]
structure Accepted (R : Rules) (S0 : State) (o : Observation) (ms : List Move) (turn : ℕ → State)
    (goal : Finset Lit) : Prop where
  observed : o.Sound R S0
  start : Determined R (settle R (observeWith S0 o)) (turn 0)
  moves : ∀ k (h : k < ms.length), ms[k] ∈ enabled R (turn k) ∧
    Determined R (settle R (step R (turn k) ms[k])) (turn (k + 1))
  goal : goal ⊆ (turn ms.length).known

-- am[implements a-jk-pf-plan-holds-closure-1019@2f78f9]
theorem Accepted.rest {R : Rules} {S0 : State} {o : Observation} {ms : List Move} {turn : ℕ → State}
    {goal : Finset Lit} (hA : Accepted R S0 o ms turn goal) : ∀ k, k ≤ ms.length → Rest R (turn k)
  | 0, _ => hA.start.rest
  | k + 1, h => (hA.moves k (by omega)).2.rest

-- am[implements a-jk-pf-plan-holds-closure-1019@2f78f9]
theorem WorldAt.rest {R : Rules} {S0 : State} {ms : List Move} {k : ℕ} {X : State}
    (h : WorldAt R S0 ms k X) : Rest R X := by
  cases h <;> assumption

-- Every world state at every turn of an accepted plan is embedded by the model's state there.
-- am[implements a-jk-pf-plan-holds-closure-1019@2f78f9]
theorem worldAt_inv {R : Rules} {S0 : State} {o : Observation} {ms : List Move} {turn : ℕ → State}
    {goal : Finset Lit} (hA : Accepted R S0 o ms turn goal) :
    ∀ {k X}, WorldAt R S0 ms k X → ∃ X0, Inv R (turn k) X X0 := by
  intro k X hw
  induction hw with
  | @zero X0 Y hX hc hY =>
    exact ⟨X0, track hA.start hc hY Relation.ReflTransGen.refl (settle_stable R _)
      (inv_settle (inv_start hA.observed hX))⟩
  | @succ k X Y h hw hc hY ih =>
    obtain ⟨X0, hI⟩ := ih
    obtain ⟨hm, hD⟩ := hA.moves k h
    obtain ⟨-, hI'⟩ := inv_ordinary hI (hA.rest k (by omega)) hw.rest hm
    exact ⟨X0, track hD hc hY Relation.ReflTransGen.refl (settle_stable R _) (inv_settle hI')⟩

-- planning_oracle.holds_everywhere for a plan the repaired planner accepts: in every world the readings
-- admit, each ordinary move is enabled at its turn, the model's state embeds the world's at every turn, and
-- every rest state after the last move holds the goal.
-- am[implements a-jk-pf-plan-holds-closure-1019@2f78f9]
theorem plan_sound {R : Rules} {S0 : State} {o : Observation} {ms : List Move} {turn : ℕ → State}
    {goal : Finset Lit} (hA : Accepted R S0 o ms turn goal) :
    (∀ k X, WorldAt R S0 ms k X → Embedded (turn k) X) ∧
    (∀ k (h : k < ms.length) X, WorldAt R S0 ms k X → ms[k] ∈ enabled R X) ∧
    (∀ X, WorldAt R S0 ms ms.length X → goal ⊆ X.known) := by
  refine ⟨fun k X hw => ?_, fun k h X hw => ?_, fun X hw => ?_⟩
  · obtain ⟨X0, hI⟩ := worldAt_inv hA hw
    exact hI.embedded
  · obtain ⟨X0, hI⟩ := worldAt_inv hA hw
    exact (inv_ordinary hI (hA.rest k (by omega)) hw.rest (hA.moves k h).1).1
  · obtain ⟨X0, hI⟩ := worldAt_inv hA hw
    exact hA.goal.trans hI.known

/-! ## Termination of a world's settling (R2)

A Derive fires only when it changes something, so it fires again only after some move writes the
negation of one of its effective writes; a Finish closes an open instance and a landing removes an act
in flight, so neither repeats. Between them only Derives fire and every signal no Derive writes stays put.
R2's live undo graph ranks the Derives, and the armed live Derives weighted by rank fall at every firing
(a-jk-pc-r2-undo-graph-1019, c-jk-pc-r2-effective-writes-1019). -/

-- A Derive's effective writes: the Achieves literals it does not read, the only ones that can change a world
-- (gc-pk-may-of).
-- am[implements a-jk-pc-r2-undo-graph-1019@fc3557]
def effective (R : Rules) (d : ℕ) : Finset Lit := (R.achieves d).toFinset.filter (fun w => w ∉ R.reads d)

-- A signal some Derive writes effectively; every other signal stays put while only Derives fire.
-- am[implements a-jk-pc-r2-undo-graph-1019@fc3557]
def derivesWrite (R : Rules) (s : ℕ) : Prop :=
  ∃ d < R.count, R.derive d = true ∧ ∃ w ∈ effective R d, w.1 = s

-- R2's live undo edge: d' writes the negation of an effective write of d, and the two read no signal that
-- no Derive writes oppositely.
-- am[implements a-jk-pc-r2-undo-graph-1019@fc3557]
def Undoes (R : Rules) (d' d : ℕ) : Prop :=
  d' < R.count ∧ d < R.count ∧ R.derive d' = true ∧ R.derive d = true ∧
  (∃ a ∈ effective R d, neg a ∈ effective R d') ∧
  ¬ ∃ r ∈ R.reads d', neg r ∈ R.reads d ∧ ¬ derivesWrite R r.1

-- R2's check passes: the live undo graph has a rank every edge lowers, which exists exactly when the
-- graph has no cycle.
-- am[implements a-jk-pc-r2-undo-graph-1019@fc3557]
def UndoRanked (R : Rules) (rank : ℕ → ℕ) : Prop := ∀ d' d, Undoes R d' d → rank d < rank d'

-- No procedure achieves a literal beside its negation (the procedure reader's rule).
-- am[implements a-jk-pf-termination-1019@096b78]
def Consistent (R : Rules) : Prop := ∀ i, ∀ w ∈ R.achieves i, neg w ∉ R.achieves i

-- In a consistent library no Derive undoes itself, so the policy's undo graph, which ignores self-edges
-- because the reader refuses a contradictory Achieves first, ranks every edge Undoes holds of.
-- am[implements a-jk-pc-r2-undo-graph-1019@fc3557]
theorem not_undoes_self {R : Rules} (hC : Consistent R) (d : ℕ) : ¬ Undoes R d d := by
  rintro ⟨-, -, -, -, ⟨a, ha, hna⟩, -⟩
  have ha' : a ∈ R.achieves d := List.mem_toFinset.1 (Finset.mem_filter.1 ha).1
  have hna' : neg a ∈ R.achieves d := List.mem_toFinset.1 (Finset.mem_filter.1 hna).1
  exact hC d a ha' hna'

-- A world: functional, its instances closed or open.
-- am[implements a-jk-pf-termination-1019@096b78]
def IsWorld (X : State) : Prop := Functional X.known ∧ ∀ i, X.inst i = .closed ∨ ∃ D, X.inst i = .opened D

-- Instances still to finish and acts still to land: only a Finish or a landing lowers it, and nothing raises it.
-- am[implements a-jk-pf-termination-1019@096b78]
def pending (R : Rules) (X : State) : ℕ := openCount R X + X.inflight.card

-- A Derive whose reads on signals no Derive writes all hold: only those can fire before the next Finish
-- or landing.
-- am[implements a-jk-pf-termination-1019@096b78]
def Live (R : Rules) (X : State) (d : ℕ) : Prop := ∀ r ∈ R.reads d, ¬ derivesWrite R r.1 → r ∈ X.known

-- A Derive with an effective write the world does not hold.
-- am[implements a-jk-pf-termination-1019@096b78]
def Armed (R : Rules) (X : State) (d : ℕ) : Prop := ¬ effective R d ⊆ X.known

open Classical in
-- The armed live Derives, each weighted by (count + 1)^rank.
-- am[implements a-jk-pf-termination-1019@096b78]
noncomputable def potential (R : Rules) (rank : ℕ → ℕ) (X : State) : ℕ :=
  ∑ d ∈ (Finset.range R.count).filter (fun d => R.derive d = true ∧ Live R X d ∧ Armed R X d),
    (R.count + 1) ^ rank d

-- am[implements a-jk-pf-termination-1019@096b78]
theorem mem_effective {R : Rules} {d : ℕ} {w : Lit} : w ∈ effective R d ↔ w ∈ R.achieves d ∧ w ∉ R.reads d := by
  simp [effective]

-- A consistent write list puts each of its literals.
-- am[implements a-jk-pf-termination-1019@096b78]
theorem mem_written_consistent {K : Finset Lit} {L : List Lit} (hL : ∀ w ∈ L, neg w ∉ L) {w : Lit}
    (hw : w ∈ L) : w ∈ written K L := by
  refine mem_written_last hw (fun v hv e => ?_)
  rcases eq_or_neg e with h | h
  · exact h
  · exact absurd (h ▸ hv) (hL w hw)

-- What a write removes: a literal the world held and no longer holds had its negation written.
-- am[implements a-jk-pf-termination-1019@096b78]
theorem neg_mem_of_removed {K : Finset Lit} {L : List Lit} {x : Lit} (hx : x ∈ K) (hn : x ∉ written K L) :
    neg x ∈ L := by
  by_contra h
  apply hn
  refine mem_written_keep hx (fun w hw e => ?_)
  rcases eq_or_neg e with h' | h'
  · exact h'
  · exact absurd (h' ▸ hw) h

-- am[implements a-jk-pf-termination-1019@096b78]
theorem pow_sum_lt {B k n : ℕ} (hB : n < B) (hk : 0 < k) : n * B ^ (k - 1) < B ^ k := by
  obtain ⟨j, rfl⟩ : ∃ j, k = j + 1 := ⟨k - 1, by omega⟩
  rw [Nat.add_sub_cancel, Nat.pow_succ]
  have h1 : 0 < B ^ j := Nat.pow_pos_iff.2 (Or.inl (by omega))
  calc n * B ^ j < B * B ^ j := Nat.mul_lt_mul_of_pos_right hB h1
    _ = B ^ j * B := Nat.mul_comm _ _

-- am[implements a-jk-pf-termination-1019@096b78]
theorem sum_le_of_subset {s t : Finset ℕ} (f : ℕ → ℕ) (h : s ⊆ t) : ∑ x ∈ s, f x ≤ ∑ x ∈ t, f x := by
  rw [← Finset.sum_sdiff h]
  exact Nat.le_add_left _ _

-- am[implements a-jk-pf-termination-1019@096b78]
theorem sum_le_card_mul {s : Finset ℕ} {f : ℕ → ℕ} {c : ℕ} (h : ∀ x ∈ s, f x ≤ c) :
    ∑ x ∈ s, f x ≤ s.card * c := by
  induction s using Finset.induction_on with
  | empty => simp
  | @insert a s ha ih =>
    rw [Finset.sum_insert ha, Finset.card_insert_of_notMem ha, Nat.succ_mul]
    have h1 := h a (Finset.mem_insert_self a s)
    have h2 := ih (fun x hx => h x (Finset.mem_insert_of_mem hx))
    omega

-- Every Derive firing lowers the potential: it disarms itself, and each Derive it arms that can still fire
-- before the next Finish or landing is one it undoes, of lower rank.
-- am[implements a-jk-pf-termination-1019@096b78]
theorem potential_derive_lt {R : Rules} {rank : ℕ → ℕ} (hR : UndoRanked R rank) (hC : Consistent R)
    {X : State} (hX : Functional X.known) {d0 : ℕ} (hp : (⟨d0, .derive⟩ : Move) ∈ priority R X) :
    potential R rank (step R X ⟨d0, .derive⟩) < potential R rank X := by
  classical
  obtain ⟨hd0c, hpa⟩ := mem_priority.1 hp
  dsimp only at hd0c hpa
  rcases (mem_priorityAt.1 hpa).2 with ⟨hd0, -, hr0, ha0⟩ | ⟨-, hpart, -⟩
  swap
  · cases hpart
  set X' := step R X ⟨d0, .derive⟩ with hX'
  have hK' : X'.known = written X.known (R.achieves d0) := rfl
  have hcons : ∀ w ∈ R.achieves d0, neg w ∉ R.achieves d0 := hC d0
  -- every literal the Derive writes is held afterwards
  have hwrit : ∀ w ∈ R.achieves d0, w ∈ X'.known := fun w hw => by
    rw [hK']; exact mem_written_consistent hcons hw
  -- signals no Derive writes keep their values
  have hstable : ∀ s v, ¬ derivesWrite R s → ((s, v) ∈ X'.known ↔ (s, v) ∈ X.known) := by
    intro s v hs
    rw [hK']
    refine written_value hX s v (fun w hw e => ?_)
    by_contra hwX
    apply hs
    refine ⟨d0, hd0c, hd0, w, mem_effective.2 ⟨hw, fun hwr => hwX (hr0 hwr)⟩, e⟩
  have hlive : ∀ d, Live R X' d ↔ Live R X d := by
    intro d
    constructor
    · intro h r hr hs
      exact (hstable r.1 r.2 hs).1 (h r hr hs)
    · intro h r hr hs
      exact (hstable r.1 r.2 hs).2 (h r hr hs)
  -- the Derive itself was live and armed, and is disarmed
  have hd0live : Live R X d0 := fun r hr _ => hr0 hr
  have hd0armed : Armed R X d0 := by
    intro hsub
    apply ha0
    intro w hw
    by_cases hwr : w ∈ R.reads d0
    · exact hr0 hwr
    · exact hsub (mem_effective.2 ⟨List.mem_toFinset.1 hw, hwr⟩)
  have hd0dis : ¬ Armed R X' d0 := fun h => h (fun w hw => hwrit w (mem_effective.1 hw).1)
  -- a Derive newly armed and live was undone by this one
  have hnew : ∀ d, d < R.count → R.derive d = true → Live R X' d → Armed R X' d → ¬ Armed R X d →
      rank d < rank d0 := by
    intro d hdc hdd hl ha hna
    apply hR d0 d
    simp only [Armed, Classical.not_not] at hna
    obtain ⟨a, ha1, ha2⟩ := Finset.not_subset.1 ha
    have haX : a ∈ X.known := hna ha1
    have hna' : neg a ∈ R.achieves d0 := neg_mem_of_removed haX (by rwa [hK'] at ha2)
    have hnae : neg a ∈ effective R d0 := by
      refine mem_effective.2 ⟨hna', fun hr => ?_⟩
      exact hX.not_neg haX (hr0 hr)
    refine ⟨hd0c, hdc, hd0, hdd, ⟨a, ha1, hnae⟩, ?_⟩
    rintro ⟨r, hr, hnr, hs⟩
    have hrX : r ∈ X.known := hr0 hr
    have hnrX' : neg r ∈ X'.known := hl (neg r) hnr hs
    have hnrX : neg r ∈ X.known := (hstable (neg r).1 (neg r).2 hs).1 hnrX'
    exact hX.not_neg hrX hnrX
  -- sums
  set B := R.count + 1
  set S := (Finset.range R.count).filter (fun d => R.derive d = true ∧ Live R X d ∧ Armed R X d)
  set S' := (Finset.range R.count).filter (fun d => R.derive d = true ∧ Live R X' d ∧ Armed R X' d)
  set N := S'.filter (fun d => d ∉ S)
  have hd0S : d0 ∈ S := Finset.mem_filter.2 ⟨Finset.mem_range.2 hd0c, hd0, hd0live, hd0armed⟩
  have hsub : S' ⊆ S.erase d0 ∪ N := by
    intro d hd
    by_cases hdS : d ∈ S
    · refine Finset.mem_union_left _ (Finset.mem_erase.2 ⟨?_, hdS⟩)
      rintro rfl
      exact hd0dis (Finset.mem_filter.1 hd).2.2.2
    · exact Finset.mem_union_right _ (Finset.mem_filter.2 ⟨hd, hdS⟩)
  have hdisj : Disjoint (S.erase d0) N := by
    rw [Finset.disjoint_left]
    intro d h1 h2
    exact (Finset.mem_filter.1 h2).2 (Finset.mem_of_mem_erase h1)
  have hNrank : ∀ d ∈ N, rank d < rank d0 := by
    intro d hd
    obtain ⟨hd', hdS⟩ := Finset.mem_filter.1 hd
    obtain ⟨hdr, hdd, hdl, hda⟩ := Finset.mem_filter.1 hd'
    refine hnew d (Finset.mem_range.1 hdr) hdd hdl hda (fun hax => hdS ?_)
    exact Finset.mem_filter.2 ⟨hdr, hdd, (hlive d).1 hdl, hax⟩
  have hNcard : N.card ≤ R.count := by
    calc N.card ≤ S'.card := Finset.card_filter_le _ _
      _ ≤ (Finset.range R.count).card := Finset.card_filter_le _ _
      _ = R.count := Finset.card_range _
  have hNsum : ∑ d ∈ N, B ^ rank d < B ^ rank d0 := by
    by_cases hN : N = ∅
    · rw [hN, Finset.sum_empty]; exact Nat.pow_pos_iff.2 (Or.inl (by omega))
    · obtain ⟨d1, hd1⟩ := Finset.nonempty_iff_ne_empty.2 hN
      have hk : 0 < rank d0 := by have := hNrank d1 hd1; omega
      have hle : ∑ d ∈ N, B ^ rank d ≤ N.card * B ^ (rank d0 - 1) :=
        sum_le_card_mul (fun d hd => Nat.pow_le_pow_right (by omega) (by have := hNrank d hd; omega))
      have h3 : N.card * B ^ (rank d0 - 1) ≤ R.count * B ^ (rank d0 - 1) := Nat.mul_le_mul_right _ hNcard
      have h4 := pow_sum_lt (B := B) (n := R.count) (by omega) hk
      omega
  have hS : ∑ d ∈ S, B ^ rank d = B ^ rank d0 + ∑ d ∈ S.erase d0, B ^ rank d :=
    (Finset.add_sum_erase S (fun d => B ^ rank d) hd0S).symm
  calc potential R rank X' = ∑ d ∈ S', B ^ rank d := rfl
    _ ≤ ∑ d ∈ S.erase d0 ∪ N, B ^ rank d := sum_le_of_subset _ hsub
    _ = ∑ d ∈ S.erase d0, B ^ rank d + ∑ d ∈ N, B ^ rank d := Finset.sum_union hdisj
    _ < ∑ d ∈ S.erase d0, B ^ rank d + B ^ rank d0 := by omega
    _ = ∑ d ∈ S, B ^ rank d := by rw [hS]; omega
    _ = potential R rank X := rfl

-- am[implements a-jk-pf-termination-1019@096b78]
theorem openCount_close_lt {R : Rules} {X : State} {i : ℕ} {D : Finset ℕ} (hi : i < R.count)
    (hXi : X.inst i = .opened D) (L : List Lit) : openCount R ((write X L).close i) < openCount R X := by
  apply Finset.card_lt_card
  refine Finset.ssubset_iff_subset_ne.2 ⟨?_, fun e => ?_⟩
  · intro j hj
    obtain ⟨hr, ho⟩ := Finset.mem_filter.1 hj
    refine Finset.mem_filter.2 ⟨hr, ?_⟩
    by_cases hji : j = i
    · subst hji; rw [close_inst_self] at ho; simp [Inst.isOpened] at ho
    · rw [close_inst_ne _ hji] at ho; exact ho
  · have hin : i ∈ (Finset.range R.count).filter (fun j => (X.inst j).isOpened) :=
      Finset.mem_filter.2 ⟨Finset.mem_range.2 hi, by simp [hXi, Inst.isOpened]⟩
    rw [← e] at hin
    have := (Finset.mem_filter.1 hin).2
    rw [close_inst_self] at this
    simp [Inst.isOpened] at this

-- am[implements a-jk-pf-termination-1019@096b78]
theorem land_inst (R : Rules) (X : State) (a : ℕ × ℕ) : (land R X a).inst = (landed X a).inst := by
  unfold land
  cases R.reaction a.1 a.2 <;> rfl

-- am[implements a-jk-pf-termination-1019@096b78]
theorem land_inflight (R : Rules) (X : State) (a : ℕ × ℕ) : (land R X a).inflight = X.inflight.erase a := by
  unfold land
  cases R.reaction a.1 a.2 <;> rfl

-- am[implements a-jk-pf-termination-1019@096b78]
theorem landed_inst_cases (X : State) (ai ae j : ℕ) :
    (landed X (ai, ae)).inst j = X.inst j ∨
      ∃ D0, X.inst j = .opened D0 ∧ (landed X (ai, ae)).inst j = .opened (insert ae D0) := by
  unfold landed
  dsimp only
  cases hx : X.inst ai with
  | opened D0 =>
    by_cases e : j = ai
    · subst e; exact Or.inr ⟨D0, hx, by simp⟩
    · left; simp [update_closed_ne e]
  | closed => exact Or.inl rfl
  | uncertain D => exact Or.inl rfl
  | completed => exact Or.inl rfl

-- am[implements a-jk-pf-termination-1019@096b78]
theorem openCount_land (R : Rules) (X : State) (a : ℕ × ℕ) : openCount R (land R X a) = openCount R X := by
  obtain ⟨ai, ae⟩ := a
  unfold openCount
  congr 1
  ext j
  simp only [Finset.mem_filter, land_inst]
  apply and_congr_right
  intro _
  rcases landed_inst_cases X ai ae j with h | ⟨D0, h1, h2⟩
  · rw [h]
  · rw [h1, h2]; simp [Inst.isOpened]

-- am[implements a-jk-pf-termination-1019@096b78]
theorem isWorld_step_prio {R : Rules} {X : State} (hX : IsWorld X) {p : Move} (hp : p ∈ priority R X) :
    IsWorld (step R X p) := by
  rcases p with ⟨i, part⟩
  obtain ⟨-, hpa⟩ := mem_priority.1 hp
  rcases (mem_priorityAt.1 hpa).2 with ⟨-, hpart, -, -⟩ | ⟨-, hpart, ⟨D, hXi, -, -⟩ | hXi⟩
  · simp only at hpart; subst hpart
    exact ⟨functional_written hX.1 _, hX.2⟩
  · simp only at hpart; subst hpart
    rw [step_finish_open hXi]
    refine ⟨functional_written hX.1 _, fun j => ?_⟩
    by_cases hji : j = i
    · subst hji; exact Or.inl (close_inst_self _ _)
    · rw [close_inst_ne _ hji]; exact hX.2 j
  · exfalso
    rcases hX.2 i with h | ⟨D, h⟩ <;> rw [hXi] at h <;> cases h

-- am[implements a-jk-pf-termination-1019@096b78]
theorem isWorld_land {R : Rules} {X : State} (hX : IsWorld X) (a : ℕ × ℕ) : IsWorld (land R X a) := by
  obtain ⟨ai, ae⟩ := a
  have hinst : ∀ j, (land R X (ai, ae)).inst j = .closed ∨ ∃ D, (land R X (ai, ae)).inst j = .opened D := by
    intro j
    rw [land_inst]
    rcases landed_inst_cases X ai ae j with h | ⟨D0, -, h2⟩
    · rw [h]; exact hX.2 j
    · exact Or.inr ⟨_, h2⟩
  refine ⟨?_, hinst⟩
  unfold land
  dsimp only
  cases R.reaction ai ae with
  | none => exact hX.1
  | some r => exact functional_written hX.1 _

-- A world settles in finitely many steps under R2: a Finish or a landing lowers what is pending, a Derive
-- leaves that and lowers the potential.
-- am[implements a-jk-pf-termination-1019@096b78]
theorem world_terminates {R : Rules} {rank : ℕ → ℕ} (hR : UndoRanked R rank) (hC : Consistent R) :
    ∀ X, IsWorld X → Acc (fun a b => WStep R true b a) X := by
  classical
  have wf : WellFounded (Prod.Lex (· < ·) (· < ·) : ℕ × ℕ → ℕ × ℕ → Prop) :=
    WellFounded.prod_lex wellFounded_lt wellFounded_lt
  suffices h : ∀ n : ℕ × ℕ, ∀ X, IsWorld X → (pending R X, potential R rank X) = n →
      Acc (fun a b => WStep R true b a) X from fun X hX => h _ X hX rfl
  intro n
  refine WellFounded.induction (C := fun n => ∀ X, IsWorld X → (pending R X, potential R rank X) = n →
    Acc (fun a b => WStep R true b a) X) wf n ?_
  intro n ih X hX hn
  constructor
  intro Y hY
  cases hY with
  | @prio p hp =>
    refine ih _ ?_ _ (isWorld_step_prio hX hp) rfl
    rw [← hn]
    rcases p with ⟨i, part⟩
    obtain ⟨hi, hpa⟩ := mem_priority.1 hp
    dsimp only at hi hpa
    rcases (mem_priorityAt.1 hpa).2 with ⟨-, hpart, -, -⟩ | ⟨-, hpart, ⟨D, hXi, -, -⟩ | hXi⟩
    · simp only at hpart; subst hpart
      have hpend : pending R (step R X ⟨i, .derive⟩) = pending R X := rfl
      rw [hpend]
      exact Prod.Lex.right _ (potential_derive_lt hR hC hX.1 hp)
    · simp only at hpart; subst hpart
      apply Prod.Lex.left
      rw [step_finish_open hXi]
      unfold pending
      have h1 := openCount_close_lt hi hXi (R.achieves i)
      have h2 : ((write X (R.achieves i)).close i).inflight.card ≤ X.inflight.card :=
        Finset.card_le_card (Finset.filter_subset _ _)
      omega
    · exfalso
      rcases hX.2 i with h | ⟨D, h⟩ <;> rw [hXi] at h <;> cases h
  | @land a _ _ ha =>
    refine ih _ ?_ _ (isWorld_land hX a) rfl
    rw [← hn]
    apply Prod.Lex.left
    unfold pending
    rw [openCount_land, land_inflight]
    have := Finset.card_erase_lt_of_mem ha
    omega

-- A world that settles in finitely many steps reaches a rest state.
-- am[implements a-jk-pf-termination-1019@096b78]
theorem exists_rest {R : Rules} {X : State} (h : Acc (fun a b => WStep R true b a) X) :
    ∃ Y, Closure R true X Y ∧ Rest R Y := by
  induction h with
  | intro X _ ih =>
    by_cases hr : Rest R X
    · exact ⟨X, Relation.ReflTransGen.refl, hr⟩
    · obtain ⟨p, hp⟩ : ∃ p, p ∈ priority R X := List.exists_mem_of_ne_nil _ hr
      obtain ⟨Y, hc, hY⟩ := ih _ (WStep.prio hp)
      exact ⟨Y, Relation.ReflTransGen.head (WStep.prio hp) hc, hY⟩


-- With admitted readings (C1) and R2, every turn of an accepted plan has a world: admission gives one at the
-- readings, and every world's settling after each ordinary move ends at a rest state.
-- am[implements a-jk-pc-c1-admitted-1019@321a3b] am[implements a-jk-pf-termination-1019@096b78]
theorem plan_nonvacuous {R : Rules} {rank : ℕ → ℕ} (hR : UndoRanked R rank) (hC : Consistent R)
    {S0 : State} {o : Observation} {ms : List Move} {turn : ℕ → State} {goal : Finset Lit}
    (hA : Accepted R S0 o ms turn goal)
    (hadm : ∃ X0, OpenWorld R S0 X0) : ∀ k ≤ ms.length, ∃ X, WorldAt R S0 ms k X := by
  intro k hk
  induction k with
  | zero =>
    obtain ⟨X0, hX0⟩ := hadm
    have hrest : Rest R X0 := by obtain ⟨_, _, _, h, _⟩ := hX0; exact h
    exact ⟨X0, WorldAt.zero hX0 Relation.ReflTransGen.refl hrest⟩
  | succ k ih =>
    obtain ⟨X, hX⟩ := ih (by omega)
    have h : k < ms.length := by omega
    obtain ⟨X0, hI⟩ := worldAt_inv hA hX
    obtain ⟨-, hI'⟩ := inv_ordinary hI (hA.rest k (by omega)) hX.rest (hA.moves k h).1
    have hW : IsWorld (step R X ms[k]) := ⟨hI'.functional, hI'.world⟩
    obtain ⟨Y, hc, hY⟩ := exists_rest (world_terminates hR hC _ hW)
    exact ⟨Y, WorldAt.succ h hX hc hY⟩

/-! ## Inquiries

An answer as an inquiry tree: matches requires each inquiry to ask a covered signal no inquiry above it
asked, so every path is finite (a-integrate-k0-inquiry-termination-1018). -/

-- am[implements a-jk-pf-finite-1019@ef14d4]
inductive Answer where
  | plan
  | dead
  | inquire (signal : ℕ) (ifTrue ifFalse : Answer)

-- am[implements a-jk-pf-finite-1019@ef14d4]
def Answer.depth : Answer → ℕ
  | .plan => 0
  | .dead => 0
  | .inquire _ t f => 1 + max t.depth f.depth

-- am[implements a-jk-pf-finite-1019@ef14d4]
def Answer.WellAsked (covered : Finset ℕ) : Finset ℕ → Answer → Prop
  | _, .plan => True
  | _, .dead => True
  | asked, .inquire s t f => s ∈ covered ∧ s ∉ asked ∧
      Answer.WellAsked covered (insert s asked) t ∧ Answer.WellAsked covered (insert s asked) f

-- No inquiry path is longer than the covered signals the inquiries above it left unasked.
-- am[implements a-jk-pf-finite-1019@ef14d4]
theorem Answer.depth_le {covered : Finset ℕ} : ∀ (a : Answer) (asked : Finset ℕ),
    a.WellAsked covered asked → a.depth ≤ (covered \ asked).card
  | .plan, _, _ => Nat.zero_le _
  | .dead, _, _ => Nat.zero_le _
  | .inquire s t f, asked, ⟨hs, hna, ht, hf⟩ => by
    have hsplit : covered \ asked = insert s (covered \ insert s asked) := by
      ext x
      simp only [Finset.mem_sdiff, Finset.mem_insert]
      constructor
      · rintro ⟨hx, hxa⟩
        by_cases e : x = s
        · exact Or.inl e
        · exact Or.inr ⟨hx, fun h => h.elim e hxa⟩
      · rintro (rfl | ⟨hx, hxa⟩)
        · exact ⟨hs, hna⟩
        · exact ⟨hx, fun h => hxa (Or.inr h)⟩
    have hcard : (covered \ asked).card = (covered \ insert s asked).card + 1 := by
      rw [hsplit, Finset.card_insert_of_notMem]
      simp
    have h1 := Answer.depth_le t _ ht
    have h2 := Answer.depth_le f _ hf
    have h3 := Nat.max_le.2 ⟨h1, h2⟩
    simp only [Answer.depth]
    omega

/-! ## Composition

Methods compose (c-integrate-planning-composition-acceptance-1017): a Finish writes its Achieves, the settle
keeps every literal no item can write the negation of, and a procedure whose When those literals cover can
start once nothing of higher priority is enabled. plan_sound then holds for every sequence so composed. -/

-- The settle keeps a known literal whose negation no procedure achieves and no act in flight writes.
-- am[implements a-jk-pf-composition-1019@e42c3b]
theorem settle_keeps {R : Rules} {S : State} {l : Lit} (hl : l ∈ S.known)
    (hp : ∀ i < R.count, neg l ∉ R.achieves i)
    (ha : ∀ a ∈ S.inflight, ∀ r, R.reaction a.1 a.2 = some r → r.2 ≠ neg l) : l ∈ (settle R S).known := by
  refine settleFuel_props R (fun S T => l ∈ S.known → (∀ a ∈ S.inflight, ∀ r, R.reaction a.1 a.2 = some r →
      r.2 ≠ neg l) → l ∈ T.known) (fun _ h _ => h) (fun S T h hl ha => h ?_ ha) _ S hl ha
  refine Finset.mem_filter.2 ⟨hl, fun hn => ?_⟩
  rcases hits_mem.1 hn with ⟨i, hi, h⟩ | ⟨a, haS, h⟩
  · obtain ⟨_, _, hw, _, _⟩ := mem_itemHits.1 h
    exact hp i hi hw
  · obtain ⟨r, er, hr, _⟩ := mem_actHits.1 h
    exact ha a haS r er hr

-- Two procedures compose: after p's Finish, a procedure q whose When p's Achieves and the kept knowledge
-- cover can start, so long as q is closed and no Finish or Derive is enabled.
-- am[implements a-jk-pf-composition-1019@e42c3b]
theorem compose_start {R : Rules} {S : State} {p q : ℕ} {D : Finset ℕ} (hC : Consistent R)
    (hpS : S.inst p = .opened D)
    (hwhen : ∀ l ∈ R.when q, l ∈ R.achieves p ∨ (l ∈ S.known ∧ ∀ w ∈ R.achieves p, w.1 ≠ l.1))
    (hkeep : ∀ l ∈ R.when q, ∀ i < R.count, neg l ∉ R.achieves i)
    (hflight : ∀ l ∈ R.when q, ∀ a ∈ S.inflight, ∀ r, R.reaction a.1 a.2 = some r → r.2 ≠ neg l)
    (hq : q < R.count) (hqd : R.derive q = false)
    (hqc : (settle R (step R S ⟨p, .finish⟩)).inst q = .closed)
    (hrest : Rest R (settle R (step R S ⟨p, .finish⟩))) :
    (⟨q, .start⟩ : Move) ∈ enabled R (settle R (step R S ⟨p, .finish⟩)) := by
  have hstep : step R S ⟨p, .finish⟩ = (write S (R.achieves p)).close p := step_finish_open hpS
  have hknown : ∀ l ∈ R.when q, l ∈ (settle R (step R S ⟨p, .finish⟩)).known := by
    intro l hl
    apply settle_keeps _ (hkeep l hl)
    · intro a ha r er
      rw [hstep, close_inflight] at ha
      exact hflight l hl a (Finset.mem_filter.1 ha).1 r er
    · rw [hstep]
      show l ∈ written S.known (R.achieves p)
      rcases hwhen l hl with h | ⟨h, hne⟩
      · exact mem_written_consistent (hC p) h
      · exact (written_other hne).2 h
  refine mem_enabled.2 (Or.inr ⟨hrest, mem_ordinary.2 ⟨hq, mem_ordinaryAt.2
    ⟨rfl, hqd, Or.inl ⟨rfl, hqc, fun l hl => hknown l hl⟩⟩⟩⟩)

/-! ## Each rule is needed

Every rule the plan theorem assumes is needed: without it one of the counterexamples planning_oracle found
at 1d48c6c goes through, here as a concrete library the kernel evaluates. Signals, actions and each
procedure's steps are numbered in the order the acceptance file's pinned worlds declare them. -/

-- A known set is functional when no two of its literals share a signal with different values.
-- am[implements a-jk-pf-necessity-1019@f85504]
theorem functional_iff (K : Finset Lit) : Functional K ↔ ∀ x ∈ K, ∀ y ∈ K, x.1 = y.1 → x = y := by
  constructor
  · intro h x hx y hy e; exact h.eq hx hy e
  · intro h s v w hv hw; exact (Prod.mk.inj (h _ hv _ hw rfl)).2

-- A relation with a two-step cycle at `x` is not well-founded there.
-- am[implements a-jk-pf-necessity-1019@f85504]
theorem not_acc_two_cycle {α : Type} {r : α → α → Prop} {x : α} (h : Acc r x) :
    ∀ y, r y x → r x y → False := by
  induction h with
  | intro x _ ih => intro y hyx hxy; exact ih y hyx x hxy hyx

-- Two states with the same fields are equal.
-- am[implements a-jk-pf-necessity-1019@f85504]
theorem State.ext' {S T : State} (hk : S.known = T.known) (hi : S.inst = T.inst) (hc : S.changed = T.changed)
    (hf : S.inflight = T.inflight) : S = T := by
  cases S; cases T; simp only at hk hi hc hf; subst hk hi hc hf; rfl

-- SIMULTANEOUS (c-jk-pf-cx-simultaneous-1019): second's act b (go, 0) and its Finish reading q (0) after b,
-- achieving not-y (1); first's act a1 (flip, 1) achieving y; flip's reaction turns not-q into q.
-- am[implements a-jk-pf-necessity-1019@f85504]
def simultaneous : Library :=
  ⟨[⟨[(1, false)], [], [⟨0, .act 0, []⟩, ⟨1, .achieve (0, true), [0]⟩]⟩,
    ⟨[(1, true)], [], [⟨0, .act 1, []⟩]⟩],
   [(1, (0, false), (0, true))]⟩

-- The model's state after the planner at 1d48c6c took second's b, then first's a1: both Finishes enabled.
-- am[implements a-jk-pf-necessity-1019@f85504]
def simultaneousRoot : State := ⟨{(0, true)}, fun i => if i < 2 then .opened {0} else .closed, {0}, ∅⟩

-- The model's rests from that root: second's Finish then first's leaves y, first's then second's not-y.
-- am[implements a-jk-pf-necessity-1019@f85504]
def simultaneousY : State :=
  settle simultaneous.compile (step simultaneous.compile
    (settle simultaneous.compile (step simultaneous.compile simultaneousRoot ⟨0, .finish⟩)) ⟨1, .finish⟩)

-- am[implements a-jk-pf-necessity-1019@f85504]
def simultaneousNotY : State :=
  settle simultaneous.compile (step simultaneous.compile
    (settle simultaneous.compile (step simultaneous.compile simultaneousRoot ⟨1, .finish⟩)) ⟨0, .finish⟩)

-- A world taking second's Finish, then first's.
-- am[implements a-jk-pf-necessity-1019@f85504]
def simultaneousWorld : State :=
  step simultaneous.compile (step simultaneous.compile simultaneousRoot ⟨0, .finish⟩) ⟨1, .finish⟩

-- R1 is needed: from that root the model's priority moves rest with y in one order and with not-y in the
-- other, so no closure is determined there, and a world taking second's Finish first rests holding y,
-- failing the goal not-y the plan claimed.
-- am[implements a-jk-pc-r1-closure-1019@f9b888] am[rests-on c-jk-pf-cx-simultaneous-1019@884a2c]
theorem r1_needed :
    (∀ M, ¬ Determined simultaneous.compile simultaneousRoot M) ∧
    ∃ X, Closure simultaneous.compile false simultaneousRoot X ∧ Rest simultaneous.compile X ∧
      (1, true) ∈ X.known := by
  have runY : Relation.ReflTransGen (MStep simultaneous.compile) simultaneousRoot simultaneousY :=
    Relation.ReflTransGen.tail (Relation.ReflTransGen.tail Relation.ReflTransGen.refl
      ⟨⟨0, .finish⟩, by decide +kernel, rfl⟩) ⟨⟨1, .finish⟩, by decide +kernel, rfl⟩
  have runN : Relation.ReflTransGen (MStep simultaneous.compile) simultaneousRoot simultaneousNotY :=
    Relation.ReflTransGen.tail (Relation.ReflTransGen.tail Relation.ReflTransGen.refl
      ⟨⟨1, .finish⟩, by decide +kernel, rfl⟩) ⟨⟨0, .finish⟩, by decide +kernel, rfl⟩
  refine ⟨fun M hD => ?_, simultaneousWorld,
    Relation.ReflTransGen.tail (Relation.ReflTransGen.tail Relation.ReflTransGen.refl
      (WStep.prio (by decide +kernel))) (WStep.prio (by decide +kernel)), by decide +kernel, by decide +kernel⟩
  have e : simultaneousY = simultaneousNotY :=
    (hD.unique _ runY (by decide +kernel)).trans (hD.unique _ runN (by decide +kernel)).symm
  have hy : (1, true) ∈ simultaneousY.known := by decide +kernel
  have hn : (1, true) ∉ simultaneousNotY.known := by decide +kernel
  exact hn (e ▸ hy)

-- SMALL_CYCLE (c-jk-pf-cx-derive-cycle-1019): p's act x (go, 0) achieving g (0); d1 reading g and a (1) and
-- writing not-a; d2 reading g and not-a and writing a.
-- am[implements a-jk-pf-necessity-1019@f85504]
def smallCycle : Library :=
  ⟨[⟨[(0, true)], [], [⟨0, .act 0, []⟩]⟩,
    ⟨[(1, false)], [], [⟨0, .achieve (0, true), []⟩, ⟨1, .achieve (1, true), []⟩]⟩,
    ⟨[(1, true)], [], [⟨0, .achieve (0, true), []⟩, ⟨1, .achieve (1, false), []⟩]⟩], []⟩

-- A world once p's Finish has written g where a held, a having moved.
-- am[implements a-jk-pf-necessity-1019@f85504]
def smallCycleWorld : State := ⟨{(0, true), (1, true)}, fun _ => .closed, {1}, ∅⟩

-- d1 then d2 bring that world back to itself.
-- am[implements a-jk-pf-necessity-1019@f85504]
theorem smallCycle_back :
    step smallCycle.compile (step smallCycle.compile smallCycleWorld ⟨1, .derive⟩) ⟨2, .derive⟩ = smallCycleWorld := by
  exact State.ext' (by decide +kernel) rfl (by decide +kernel) rfl

-- R2 is needed: d1 and d2 undo each other's effective writes, so no rank orders the undo graph, and the
-- world never rests.
-- am[implements a-jk-pc-r2-undo-graph-1019@fc3557] am[rests-on c-jk-pf-cx-derive-cycle-1019@93ff37]
theorem r2_needed :
    (¬ ∃ rank, UndoRanked smallCycle.compile rank) ∧
    ¬ Acc (fun a b => WStep smallCycle.compile true b a) smallCycleWorld := by
  refine ⟨fun ⟨rank, h⟩ => ?_, fun hacc => ?_⟩
  · have h12 : Undoes smallCycle.compile 1 2 := by unfold Undoes derivesWrite; decide +kernel
    have h21 : Undoes smallCycle.compile 2 1 := by unfold Undoes derivesWrite; decide +kernel
    have := h 1 2 h12
    have := h 2 1 h21
    omega
  · have back := WStep.prio (landing := true) (R := smallCycle.compile)
      (S := step smallCycle.compile smallCycleWorld ⟨1, .derive⟩) (m := ⟨2, .derive⟩) (by decide +kernel)
    rw [smallCycle_back] at back
    exact not_acc_two_cycle hacc (step smallCycle.compile smallCycleWorld ⟨1, .derive⟩)
      (WStep.prio (by decide +kernel)) back

-- TRANSIENT_FINISH (c-jk-pf-cx-transient-finish-1019): i's act k (go, 0) and its Finish reading l (1) after
-- k, achieving not-x (0) and not-l; d1 reading x and writing l; setter's acts a (flip, 1) and b (go) after a,
-- achieving z (2); flip's reaction turns not-l into l. The snapshot has k receipted and l refuted.
-- am[implements a-jk-pf-necessity-1019@f85504]
def transient : Library :=
  ⟨[⟨[(0, false), (1, false)], [], [⟨0, .act 0, []⟩, ⟨1, .achieve (1, true), [0]⟩]⟩,
    ⟨[(1, true)], [], [⟨0, .achieve (0, true), []⟩]⟩,
    ⟨[(2, true)], [], [⟨0, .act 1, []⟩, ⟨1, .act 0, [0]⟩]⟩],
   [(1, (1, false), (1, true))]⟩

-- am[implements a-jk-pf-necessity-1019@f85504]
def transientSnapshot : State := ⟨{(1, false)}, fun i => if i = 0 then .opened {0} else .closed, ∅, ∅⟩

-- The world where x held before the readings.
-- am[implements a-jk-pf-necessity-1019@f85504]
def transientStart : State := ⟨{(0, true), (1, false), (2, false)}, transientSnapshot.inst, ∅, ∅⟩

-- That world's rest: d1 fires, then i's Finish.
-- am[implements a-jk-pf-necessity-1019@f85504]
def transientRest : State :=
  step transient.compile (step transient.compile transientStart ⟨1, .derive⟩) ⟨0, .finish⟩

-- R3 is needed: the world where x held settles, d1 then i's Finish firing, to a rest the readings admit
-- with i closed, while the snapshot settled without classifying its instances keeps i open, so it embeds
-- no state of that world.
-- am[implements a-jk-pc-r3-exact-amend-1019@9a3391] am[rests-on c-jk-pf-cx-transient-finish-1019@b0e89c]
theorem r3_needed :
    ∃ X0, OpenWorld transient.compile transientSnapshot X0 ∧
      ¬ Embedded (settle transient.compile transientSnapshot) X0 := by
  refine ⟨transientRest, ⟨transientStart, ⟨(functional_iff _).2 (by decide +kernel), fun i => ?_, rfl⟩,
    Relation.ReflTransGen.tail (Relation.ReflTransGen.tail Relation.ReflTransGen.refl
      (WStep.prio (by decide +kernel))) (WStep.prio (by decide +kernel)), by decide +kernel, by decide +kernel⟩,
    fun ⟨_, hcert, _⟩ => ?_⟩
  · simp only [transientStart, transientSnapshot]
    split_ifs <;> rfl
  · obtain ⟨D', hX, -⟩ := hcert 0 {0} (by decide +kernel)
    have hc : transientRest.inst 0 = .closed := by decide +kernel
    rw [hc] at hX
    cases hX

-- MEASURED (c-integrate-planner-empty-world-plan-1019): derive_b reads a (0) and writes b (1); a is
-- detected and b refuted.
-- am[implements a-jk-pf-necessity-1019@f85504]
def measured : Library := ⟨[⟨[(1, true)], [], [⟨0, .achieve (0, true), []⟩]⟩], []⟩

-- am[implements a-jk-pf-necessity-1019@f85504]
def measuredSnapshot : State := ⟨{(0, true), (1, false)}, fun _ => .closed, ∅, ∅⟩

-- The model's rest once derive_b fires.
-- am[implements a-jk-pf-necessity-1019@f85504]
def measuredRest : State :=
  settle measured.compile (step measured.compile (settle measured.compile measuredSnapshot) ⟨0, .derive⟩)

-- C1 is needed: the model's own closure from those readings reaches b, the plan the planner at 410fc76a
-- gave, while no world rests holding the readings, so every claim about that plan's worlds is vacuous.
-- am[implements a-jk-pc-c1-admitted-1019@321a3b] am[rests-on c-integrate-planner-empty-world-plan-1019@1d202f]
theorem c1_needed :
    (Relation.ReflTransGen (MStep measured.compile) (settle measured.compile measuredSnapshot) measuredRest ∧
      Rest measured.compile measuredRest ∧ (1, true) ∈ measuredRest.known) ∧
    ¬ ∃ X0, OpenWorld measured.compile measuredSnapshot X0 := by
  refine ⟨⟨Relation.ReflTransGen.tail Relation.ReflTransGen.refl ⟨⟨0, .derive⟩, by decide +kernel, rfl⟩,
    by decide +kernel, by decide +kernel⟩, ?_⟩
  rintro ⟨X0, W, hW, hc, hrest, hk⟩
  have hf := (initial_closure hW hc).1
  have hb : (1, false) ∈ X0.known := hk (by decide +kernel)
  have hreads : measured.compile.reads 0 = {(0, true)} := by decide +kernel
  have hp : (⟨0, .derive⟩ : Move) ∈ priority measured.compile X0 := by
    refine mem_priority.2 ⟨by decide +kernel, mem_priorityAt.2 ⟨rfl, Or.inl ⟨by decide +kernel, rfl, ?_, ?_⟩⟩⟩
    · rw [hreads]
      intro l hl
      rw [Finset.mem_singleton.1 hl]
      exact hk (by decide +kernel)
    · intro h
      have h1 : (1, true) ∈ X0.known := h (by decide +kernel)
      exact absurd (hf.eq h1 hb rfl) (by decide)
  unfold Rest at hrest
  rw [hrest] at hp
  simp at hp

/-! ## Conformance

`main` checks the executable model against planning_oracle on tests/data/planning_model_conformance.json,
which tests/record_planning_model_conformance.py records: for each case it observes the state under the
recorded classification, settles it, and compares the start state, the moves enabled there and the state
each leaves with what the oracle answered (a-jk-pf-conformance-1019). -/

namespace Conformance

open Lean

-- am[implements a-jk-pf-conformance-1019@8a012a]
def lit (j : Json) : Except String Lit :=
  match j with
  | .arr #[s, v] => return (← s.getNat?, ← v.getBool?)
  | _ => throw s!"a literal is [signal, value], not {j.compress}"

-- am[implements a-jk-pf-conformance-1019@8a012a]
def list {α : Type} (f : Json → Except String α) (j : Json) : Except String (List α) := do
  (← j.getArr?).toList.mapM f

-- am[implements a-jk-pf-conformance-1019@8a012a]
def field {α : Type} (f : Json → Except String α) (j : Json) (name : String) : Except String α := do
  f (← j.getObjVal? name)

-- am[implements a-jk-pf-conformance-1019@8a012a]
def step (j : Json) : Except String Step := do
  let id ← field Json.getNat? j "id"
  let after ← field (list Json.getNat?) j "after"
  match ← field Json.getStr? j "kind" with
  | "act" => return ⟨id, .act (← field Json.getNat? j "action"), after⟩
  | "investigate" => return ⟨id, .investigate, after⟩
  | "achieve" => return ⟨id, .achieve (← field lit j "literal"), after⟩
  | kind => throw s!"no step kind {kind}"

-- am[implements a-jk-pf-conformance-1019@8a012a]
def procedure (j : Json) : Except String Procedure :=
  return ⟨← field (list lit) j "achieves", ← field (list lit) j "when", ← field (list step) j "steps"⟩

-- am[implements a-jk-pf-conformance-1019@8a012a]
def reaction (j : Json) : Except String (ℕ × Lit × Lit) :=
  match j with
  | .arr #[a, r, w] => return (← a.getNat?, ← lit r, ← lit w)
  | _ => throw s!"a reaction is [action, read, write], not {j.compress}"

-- am[implements a-jk-pf-conformance-1019@8a012a]
def library (j : Json) : Except String Library :=
  return ⟨← field (list procedure) j "procedures", ← field (list reaction) j "reactions"⟩

-- am[implements a-jk-pf-conformance-1019@8a012a]
def pair (j : Json) : Except String (ℕ × ℕ) :=
  match j with
  | .arr #[i, e] => return (← i.getNat?, ← e.getNat?)
  | _ => throw s!"an act is [procedure, step], not {j.compress}"

-- am[implements a-jk-pf-conformance-1019@8a012a]
def entry (j : Json) : Except String (ℕ × Finset ℕ) :=
  match j with
  | .arr #[i, d] => return (← i.getNat?, (← list Json.getNat? d).toFinset)
  | _ => throw s!"an instance is [procedure, done steps], not {j.compress}"

-- A recorded state: each procedure's instance completed, open, uncertain or else closed.
-- am[implements a-jk-pf-conformance-1019@8a012a]
def state (j : Json) : Except String State := do
  let opened ← field (list entry) j "open"
  let uncertain ← field (list entry) j "uncertain"
  let completed ← field (list Json.getNat?) j "completed"
  let inst : ℕ → Inst := fun i =>
    if i ∈ completed then .completed
    else match opened.lookup i, uncertain.lookup i with
      | some D, _ => .opened D
      | none, some D => .uncertain D
      | none, none => .closed
  return ⟨(← field (list lit) j "known").toFinset, inst, (← field (list Json.getNat?) j "changed").toFinset,
    (← field (list pair) j "inflight").toFinset⟩

-- am[implements a-jk-pf-conformance-1019@8a012a]
def observation (j : Json) : Except String Observation := do
  let completes ← field (list Json.getNat?) j "completes"
  let keeps ← field (list Json.getNat?) j "keeps"
  return ⟨fun i => decide (i ∈ completes), fun i => decide (i ∈ keeps), (← field (list lit) j "entailed").toFinset⟩

-- am[implements a-jk-pf-conformance-1019@8a012a]
def move (j : Json) : Except String Move :=
  match j with
  | .arr #[i, .str "start"] => return ⟨← i.getNat?, .start⟩
  | .arr #[i, .str "finish"] => return ⟨← i.getNat?, .finish⟩
  | .arr #[i, .str "derive"] => return ⟨← i.getNat?, .derive⟩
  | .arr #[i, e] => return ⟨← i.getNat?, .step (← e.getNat?)⟩
  | _ => throw s!"a move is [procedure, part], not {j.compress}"

-- Where two states differ for a library of `n` procedures, or none.
-- am[implements a-jk-pf-conformance-1019@8a012a]
def differ (n : ℕ) (S T : State) : Option String :=
  if S.known ≠ T.known then some "known"
  else if S.changed ≠ T.changed then some "changed"
  else if S.inflight ≠ T.inflight then some "inflight"
  else ((List.range n).find? (fun i => decide (S.inst i ≠ T.inst i))).map (fun i => s!"instance {i}")

-- Every difference between the model and the oracle on one recorded case of a world's library.
-- Time: one settle of the observed state and one per enabled move.
-- am[implements a-jk-pf-conformance-1019@8a012a]
def check (world : String) (R : Rules) (j : Json) : Except String (List String) := do
  let name := s!"{world} {← field Json.getStr? j "name"}"
  let M := settle R (observeWith (← field state j "snapshot") (← field observation j "observation"))
  let moves ← field (list move) j "enabled"
  let successors ← field (list state) j "successors"
  let found := enabled R M
  let start := (differ R.count M (← field state j "start")).map (s!"{name}: the start state differs in " ++ ·)
  let enabledDiffer := if moves.length == found.length && moves.all (found.contains ·) then none
    else some s!"{name}: the oracle enables {repr moves}, the model {repr found}"
  let after := (moves.zip successors).filterMap (fun (m, T) =>
    (differ R.count (apply R M m) T).map (s!"{name}: the state {repr m} leaves differs in " ++ ·))
  return start.toList ++ enabledDiffer.toList ++ after

-- Every difference on the whole record, with the number of cases checked.
-- am[implements a-jk-pf-conformance-1019@8a012a]
def checkAll (record : Json) : Except String (ℕ × List String) := do
  let mut checked := 0
  let mut differences := []
  for world in ← (← record.getObjVal? "worlds").getArr? do
    let name ← field Json.getStr? world "name"
    let R := (← field library world "library").compile
    for c in ← (← world.getObjVal? "cases").getArr? do
      checked := checked + 1
      differences := differences ++ (← check name R c)
  return (checked, differences)

end Conformance

end GoalChainerPlanningModel

open GoalChainerPlanningModel in
-- lean --run proofs/PlanningModel.lean RECORD: exit 0 when the model answers as the oracle did on every
-- recorded case, 1 naming each difference, 2 for a record it cannot read.
-- am[implements a-jk-pf-conformance-1019@8a012a]
def main (args : List String) : IO UInt32 := do
  let [path] := args | IO.eprintln "usage: lean --run PlanningModel.lean RECORD"; return 2
  match Lean.Json.parse (← IO.FS.readFile path) >>= Conformance.checkAll with
  | .error problem => IO.eprintln s!"conformance: {problem}"; return 2
  | .ok (checked, differences) =>
    for difference in differences do
      IO.eprintln difference
    IO.println s!"conformance: {checked} cases, {differences.length} differences"
    return if differences.isEmpty then 0 else 1

#print axioms GoalChainerPlanningModel.plan_sound
#print axioms GoalChainerPlanningModel.plan_nonvacuous
#print axioms GoalChainerPlanningModel.world_terminates
#print axioms GoalChainerPlanningModel.settle_stable
#print axioms GoalChainerPlanningModel.settle_rounds
#print axioms GoalChainerPlanningModel.journal_sets_no_literal
#print axioms GoalChainerPlanningModel.exactObservation_sound
#print axioms GoalChainerPlanningModel.not_undoes_self
#print axioms GoalChainerPlanningModel.Answer.depth_le
#print axioms GoalChainerPlanningModel.compose_start
#print axioms GoalChainerPlanningModel.r1_needed
#print axioms GoalChainerPlanningModel.r2_needed
#print axioms GoalChainerPlanningModel.r3_needed
#print axioms GoalChainerPlanningModel.c1_needed
