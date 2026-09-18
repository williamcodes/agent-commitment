# Williams (2026) on commitment: source notes

Source: Iwan Williams, "Intention-like representations in language models?", *Philosophical Studies*
(forthcoming, 2026). Preprint v2 (updated 11 March 2026) on PhilArchive:
<https://philarchive.org/rec/WILIRI-4>. Page numbers below refer to the preprint PDF.

These notes were written **before** any experimental run, and the rubric in `rubric-v1.md` was
derived from them. Quotations are kept short; the reader should consult the preprint for context.

## The five properties (§2, p. 5)

Williams surveys five properties associated with intentions: (1) directive function, (2) degrees of
distality, (3) degrees of abstraction, (4) commitment, (5) planning. He notes that some are
"representation-level properties" and others "system-level features, to which intentions make a
characteristic contribution", and makes "no claim as to whether these features are individually
necessary or jointly sufficient for intentions".

## Commitment (§2.4, pp. 7–8)

Intentions differ from desires in involving commitment. Desires are inputs to deliberation;
intentions are "the outputs of deliberation, and mark the point at which an agent settles on one
possibility from a range of candidates". Williams separates commitment into **three aspects**:

1. **Executive / conduct-controlling.** Intentions are an "executive attitude" (Mele) or are
   "conduct-controlling" (Bratman): all else equal, they cause the intended action, whereas desires
   merely potentially influence action.
2. **Settling among alternatives.** Intentions "settle among conflicting desires or alternative
   courses of action", so an agent "will thus tend to form a mutually consistent set of
   intentions", which is not true of desires.
3. **Stability / inertia.** After setting an intention "one normally ceases deliberation on the
   relevant issue"; intentions are "terminators of practical reasoning" (Pacherie & Haggard) and
   "resistant to reconsideration". Footnote 8 (citing Holton 2009) is important for our design:
   reconsideration "is not impossible"; stability implies "a shift in the threshold of relevance of
   information", so some information that would have mattered when forming the intention will
   not suffice to provoke rational reconsideration afterwards.

Commitment is what makes it possible "to make further plans on the presumption that one will
follow through as intended".

## Planning (§2.5, pp. 8–9)

Intentions "frame" subsequent deliberation in two ways: (a) they "constrain and prompt means-end
reasoning"; (b) horizontal constraints: intentions "act as a 'filter' on the formation of subsequent
intentions", "ruling out courses of action that are inconsistent with what one already intends".

## What Williams finds lacking in LLM representations (§4.4, pp. 21–23; §4.5 p. 25; Table 1 p. 26)

The candidate representations are *planning features* (Lindsey et al. 2025, the rhyming-couplet
"rabbit" case) and *function vectors / output features* (Todd et al. 2024; Hendel et al. 2024).

- On **settling**: the model "do[es] not activate a single planning feature, instead simultaneously
  activating representations of alternative end words" ("rabbit", "habit", "crab, it"). Because
  these outcomes "are not compossible, this falls afoul of a key dimension of the commitment
  characteristic of intentions, namely that they settle among a pool of inconsistent options".
  Even the most active candidate "does not appear to 'shield' an outcome from competitors" (the
  couplet ended with "rabbit" only 81% of the time).
- On **stability**: self-attention carries information across token positions, "a loose analogue of
  maintaining representations across time", but *contextualisation errors* (Lepori et al. 2025)
  show cross-position maintenance can break down: a model outputs a context-appropriate word,
  then later "revert[s] to a context-inappropriate output". Footnote 22 adds behavioural evidence
  from hangman (Baldelli et al. 2026): a model as word-setter reveals "AWAKING" midway, then
  accepts guesses inconsistent with it and finally accepts "ANATOMY", suggesting models "do not
  commit to a single hidden word through a game's duration".
- On **planning**: because inconsistent directive representations persist alongside each other,
  they "at most impose soft constraints" on later directive representations, whereas intentions are
  thought to "impose hard constraints in planning".
- Table 1 summary (commitment row): similarity: representations can be carried forward across
  positions; differences: alternatives co-occur and causally influence output; contextualisation
  errors suggest a lack of stability. Conclusion (§6): the most notable differences are "their failure
  to play a consistently directive function, and their failure to firmly settle between inconsistent
  outcomes".
- §5.2: with respect to commitment "output features and planning features appear closer to
  desires than intentions".

## Points that matter for our design

1. Williams's unit of analysis is an internal representation inside a single forward pass or
   generation; his evidence is interpretability evidence (features, activations) plus two
   behavioural examples (contextualisation errors, hangman). The hangman example is already a
   whole-system behavioural observation, so behavioural evidence is in scope for him.
2. His three aspects translate naturally into behavioural measures for an agent:
   (1) conduct-control: does the choice show up in files and commands, not only in text;
   (2) settling: does the agent avoid implementing incompatible alternatives side by side;
   (3) stability: does the choice survive later steps and *irrelevant* temptations, while
   (footnote 8) remaining revisable when *relevant* information arrives.
   Planning maps to: are later features built on the chosen approach (means-end framing), and
   are inconsistent options filtered out (horizontal constraint).
3. He explicitly leaves open that "descendants of current LLMs may close the gap", including
   "augmentations to the basic transformer architecture". An agent harness is such an augmentation.
4. Nothing in the behavioural tests below can show that any *internal representation* satisfies
   his causal-representational account. Evidence at the system level is evidence for a different
   (weaker, or at least different) claim.
