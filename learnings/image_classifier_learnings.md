# Image Classifier Learnings (PyTorch, Transfer Learning)

## Task Setup
- Multi-class, single-label image classification (e.g. 8 breed classes) using `torchvision.datasets.ImageFolder` — labels are assigned automatically from subfolder names, no manual labelling needed.
- Data split via `random_split`; a "train/test split" in code is often functionally a **validation split** — the true held-out test set is separate and unseen during development.

## Choosing a Backbone
- Pretrained torchvision backbones (transfer learning) are usually far more effective than training from scratch, especially on small datasets (~1000 images/class).
- Model size scales roughly linearly with parameter count: **size (MB) ≈ params × 4 / 1,000,000** (float32). Useful for checking against a submission size limit before training.
- Compact options ranked by params: MobileNetV2/V3 < EfficientNet-B0/B1/B2 < RegNet-Y variants < ResNet18 < ResNet50/ConvNeXt (much larger).
- EfficientNet variants (B0→B7) use **compound scaling** — width, depth, and *input resolution* all increase together. Each variant's pretrained weights expect a specific input resolution (documented in each model's `Weights.transforms()`); this resolution mismatch matters when your images are much smaller (e.g. 80×80) than what a variant was designed for.
- RegNet architectures come from a systematic *design-space search* (not hand-designed); "GF" in the name denotes the FLOP compute budget searched within. RegNet-Y includes squeeze-and-excitation (SE) blocks.
- SE blocks: a channel-attention mechanism — "squeeze" (global average pool per channel) then "excitation" (small FC network + sigmoid) produces per-channel reweighting, letting the network emphasise the most informative feature channels.
- **Key finding from experimentation:** a "better" ImageNet-benchmark backbone does not guarantee better results on a small, low-resolution, task-specific dataset. Two backbones with a meaningful ImageNet accuracy gap converged to the *same* validation accuracy on the actual small dataset — the bottleneck was the data/resolution, not backbone capacity. Always verify empirically rather than assuming from ImageNet leaderboards.
- Freezing the backbone (training only a new classifier head) is faster and regularises harder, but can leave real accuracy on the table if the frozen features aren't sufficiently adapted; full fine-tuning (unfrozen backbone, small LR) generally reaches a higher ceiling if data volume allows it.

## Adapting a Pretrained Model
- Replace only the final classification layer, reading its existing `in_features` dynamically (e.g. `model.fc.in_features` or `model.classifier[1].in_features`) rather than hardcoding — the exact attribute name/structure varies by architecture family (`.fc` for ResNet/RegNet, `.classifier` Sequential for EfficientNet).
- The new head has **randomly initialised** weights — only the backbone is pretrained.
- Output raw logits — never add a Softmax/Sigmoid layer if using `CrossEntropyLoss`, which applies `log_softmax` internally. Adding it manually causes a "double softmax" bug: wrong loss values, degraded/vanishing gradients, and possible numerical instability (large logits overflowing an un-fused softmax).
- To **freeze** a backbone: set `param.requires_grad = False` on all backbone parameters *before* replacing the classifier head (so the freeze loop doesn't also disable the new head). Optionally filter the optimizer to only trainable params: `filter(lambda p: p.requires_grad, model.parameters())`.

## Preprocessing & Normalisation
- If using ImageNet-pretrained weights, normalise inputs with ImageNet's mean/std (`[0.485, 0.456, 0.406]` / `[0.229, 0.224, 0.225]`) — required for the pretrained features to behave as intended, both for training and validation/test transforms.
- Normalisation is **preprocessing**, not augmentation — apply identically at train and test time.
- Deterministic preprocessing (resize, tensor conversion, normalisation) can be applied to validation/test data; only **random augmentation** should be train-only.
- If the test set is guaranteed to be same-resolution/same-source as training data, resizing/cropping the test transform is unnecessary and can even hurt (e.g. an unneeded CenterCrop would discard real content the model never learned to expect).

## Data Augmentation
- Augmentation exposes the model to varied versions of each training image, reducing memorisation of exact pixel patterns — a primary and highly effective lever against overfitting.
- Useful for natural photos: `RandomResizedCrop` (crop % of area + resize — varies framing/zoom), `RandomHorizontalFlip`, `RandomRotation` (mild ±angle), `RandomAffine` (translation/shear).
- `RandomResizedCrop` vs `RandomAffine(translate=...)`: the former crops-then-resizes (zooms, no padding); the latter shifts the same-scale content within a fixed frame (padding appears at vacated edges). Different effects, often used together.
- Colour-preserving caution: if colour/pattern is a genuinely discriminative feature for the classes, avoid hue jitter and grayscale; keep saturation/contrast/brightness changes mild.
- **`TrivialAugmentWide()`** — applies one randomly chosen operation (from a pool including rotation, shear, translate, brightness, contrast, saturation, sharpness, posterize, solarize, autocontrast, colour) at a randomly sampled magnitude, per image, per call.
  - Empirically very effective: applying it can close a large train/validation accuracy gap (e.g. ~9% down to ~2%) while holding or slightly improving validation accuracy — because training accuracy is pulled down toward validation (less memorisation) rather than validation degrading.
  - Works well largely because of randomness itself (variety, self-limiting magnitude/frequency) rather than a hand-tuned policy; effectiveness holds even though it can occasionally distort colour, since only one operation applies per image at variable, often-mild strength.
  - Order matters: PIL-based transforms (crop, flip, rotate, jitter, TrivialAugmentWide) come before `ToTensor()`; tensor-based ones (`Normalize`, `RandomErasing`) come after.
- Other options worth knowing: `RandomErasing` (blanks a patch — good, complementary occlusion robustness), `GaussianBlur` (mild focus-variation), `RandomPerspective` (mild viewpoint change). Avoid `RandomVerticalFlip` and `Grayscale`/`RandomGrayscale` for natural, colour-dependent classification tasks. `MixUp`/`CutMix` operate on batches, not single images — not usable via a simple per-image `transform()` function.

## Loss Function
- `CrossEntropyLoss` is standard for single-label multi-class classification; expects raw logits, applies `log_softmax` internally.
- **Label smoothing** (`label_smoothing=ε`): true-class target becomes `1-ε`, remainder `ε` split evenly among the *other* classes (not all classes). Discourages overconfident predictions; useful when some classes are visually similar/easily confused — improves generalisation, especially where inherent ambiguity exists between class pairs.
- `NLLLoss` is mathematically equivalent to cross-entropy but requires manually applying `LogSoftmax` first — more error-prone, no benefit over `CrossEntropyLoss`.
- Focal loss targets class imbalance — unnecessary on a balanced dataset.

## Optimiser
- **AdamW** vs plain **Adam**: standard Adam couples weight decay into the gradient (L2-style), where it then gets scaled by Adam's adaptive per-parameter learning rate — weakening/distorting the intended regularisation. AdamW decouples weight decay, applying it directly to parameters, giving more predictable, effective regularisation. This is well-documented in the literature (Loshchilov & Hutter, "Decoupled Weight Decay Regularization").
- SGD+momentum can sometimes generalise *better* on image tasks (theory: noisier updates find flatter minima), but is far more sensitive to learning-rate choice and typically needs more tuning/epochs to match Adam-family convergence — a real trade-off, not a clear-cut "one is always better."
- For fine-tuning tasks close to the pretraining domain (e.g. natural images close to ImageNet), AdamW and SGD often perform comparably; AdamW's practical ease of use (less LR sensitivity) is the main reason to default to it, not a decisive theoretical accuracy edge.
- Use a small learning rate (e.g. 1e-4) when fine-tuning a pretrained model to avoid destroying useful pretrained weights; SGD generally needs a much larger LR (e.g. 1e-2) than Adam-family optimisers since it lacks adaptive per-parameter scaling.
- A **differential learning rate** (lower on the pretrained backbone, higher on the new head) is a reasonable idea in theory but can backfire in practice if the head's LR is set too high — worth testing carefully, not assuming it helps.

## Learning Rate Scheduling
- **Cosine annealing** smoothly decays the learning rate from its initial value toward (near) zero over the course of training (`T_max` = training length, e.g. total epochs), rather than a fixed or step-drop schedule. Large early updates enable fast initial progress; small late updates allow precise convergence.

## Overfitting & the Train/Validation Gap
- Rule of thumb: gap under ~10 percentage points is broadly normal/acceptable; much larger gaps (>15-20 points) more strongly indicate overfitting — but there's no fixed universal threshold, and this shouldn't be the only signal used.
- A smaller gap is only meaningful if validation accuracy holds or improves — closing the gap by dragging *validation* down (underfitting) is a worse outcome, not a better one. Always check whether a change lifted validation, not just narrowed the gap.
- Levers to reduce a training/validation gap, roughly in order of typical effectiveness for image tasks: **stronger/more varied data augmentation** > dropout > weight decay > reducing model capacity/epochs. Empirically, augmentation often outperforms dropout/weight-decay tweaks by a wide margin.
- It's normal and not a bug for **validation accuracy to exceed training accuracy** — usually because regularisation (dropout, heavy augmentation) is applied only during training, making the training task itself harder than the (clean, eval-mode) validation evaluation.
- If validation accuracy plateaus across many epochs and multiple backbone/hyperparameter changes, this is a strong signal you've hit a genuine ceiling set by the data itself (resolution, inherent inter-class ambiguity) rather than the model or training setup — confirm via the confusion matrix: spread-out, non-dominant confusions across many classes (rather than one clearly fixable pair) support this conclusion.
- Small accuracy differences (<~1%) between runs/configs are often within normal run-to-run noise (random split, augmentation, initialisation, shuffling) — don't over-interpret them as proof one configuration is better without repeated runs.

## Validation Set Usage & Final Training
- Standard workflow: hold out a validation split (e.g. 80:20) during development to tune architecture/hyperparameters and monitor over/underfitting: this is model *selection*, not final evaluation.
- Optionally retrain the finalised configuration on the *full* dataset (no held-out split) for the final/submitted model — uses more data, typically gives a small reliable improvement, but sacrifices the ability to measure validation accuracy for that final run (there is no held-out set left).
- When training on the full dataset, no validation accuracy is available for the final weights — report the earlier validation-split figure as your model-selection evidence, and clearly label full-dataset run figures as **training** accuracy, not validation/test accuracy, to avoid conflating different metrics.
- A trained/saved model checkpoint is deterministic on a fixed dataset — the same checkpoint always reproduces the same accuracy on the same data it's evaluated against. Validation-set accuracy is not a guarantee of performance on genuinely unseen (e.g. hidden test) data, since that data wasn't used to select/tune anything.

## Practical/Environment Notes
- Relative file paths resolve against the current working directory, not the script's location — must `cd` into the correct folder before running a script that uses relative paths.
- On Windows, use raw strings (`r"C:\path\to\folder"`) or forward slashes for file paths — unescaped backslashes can be misinterpreted as escape characters.
- For cloud GPU training (e.g. Google Colab): mount cloud storage for persistence, but copy/unzip bulk data to the local/ephemeral fast disk for training speed (reading many small files directly from mounted cloud storage is slow); persistent notebooks retain code cells between sessions but not the runtime state (mounted drives, unpacked files, installed packages) — these must be re-established each new session.
