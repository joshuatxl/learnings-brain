# Neural Networks & CNNs — Study Notes

A reference of practical methods and concepts for building and reasoning about neural networks in PyTorch, covering CNNs (LeNet-style) and fully-connected / densely-connected networks.

---

## 1. Building blocks in PyTorch

### `nn.Module`
Every network is a class inheriting from `torch.nn.Module`, with two parts:
- `__init__`: call `super().__init__()`, then declare each layer as an attribute (this registers its learnable parameters so the optimizer can find them).
- `forward(self, x)`: defines how data flows through the layers. Called automatically via `net(x)` — never call `.forward()` directly.

### `nn.Linear(in_features, out_features)` — fully connected layer
- Computes `y = xAᵀ + b` (an affine transformation) — a weighted sum of every input plus a bias.
- `in_features` = number of input values; `out_features` = number of output values (nodes).
- Operates on **flat vectors**, not spatial grids. No `kernel_size`/`stride`/`padding` — those are convolution-only.
- **Rule:** each layer's `in_features` must equal the previous layer's `out_features` (one layer's output becomes the next's input).

### `nn.Conv2d(in_channels, out_channels, kernel_size, ...)` — convolutional layer
- Slides `out_channels` learnable filters (each `kernel_size × kernel_size × in_channels`) across a spatial input, producing `out_channels` feature maps.
- **Kernel size** = dimensions of the sliding filter window (e.g. `5` → a 5×5 grid of weights). At each position it computes a weighted sum of the patch beneath it.
- Each output filter looks across **all** input channels simultaneously (so a filter is `k × k × in_channels` deep).
- `out_channels` (number of feature maps) is a **design choice** you set — not derived from data. Common pattern: increase channels with depth as spatial size shrinks.

### `nn.MaxPool2d(kernel_size)`
- Takes the max value in each non-overlapping window (e.g. 2×2), halving spatial dimensions. No learnable parameters. Adds translation invariance and reduces computation.

### Activations
- `torch.tanh` — squashes to `[-1, 1]`; use for hidden layers.
- `torch.sigmoid` — squashes to `[0, 1]`; use on output for binary classification (produces a probability).
- `F.relu` — zeroes negatives, keeps positives. Has no learnable parameters, so it's typically called inline in `forward()` rather than declared in `__init__`.

---

## 2. Channels vs. nodes vs. features

- **Feature / node** (in a Linear layer): a single scalar value.
- **Channel** (in a Conv layer): an entire 2D grid (feature map) of values, not a single number.
- Flattening a conv output before a Linear layer requires multiplying **channels × height × width**, because each channel is a whole grid, not one value.

---

## 3. Tracking spatial size through a CNN

Two things change spatial size:

**Convolution** (no padding): `out = in − kernel_size + 1`
**Padding**: adds a zero border; `padding=p` adds `p` pixels on every side, so effective input grows by `2p` per dimension.
- `kernel=3, padding=1` **preserves** spatial size exactly.
- `kernel=5, padding=2` also preserves size (used to make 28×28 MNIST behave like LeNet's expected 32×32).
**Max pooling** (2×2): halves each spatial dimension.

### Why padding matters (visually)
Without padding, a filter can't hang off the edge, so edge pixels get "seen" less and the output shrinks each conv. Padding gives the filter room to center on edge pixels too, treating all pixels equally and (with the right amount) keeping output size equal to input.

### Worked example — LeNet-5 on 28×28 input
```
conv1 (1→6, k5, pad2):  1@28×28 → 6@28×28   (padded to 32, 32−5+1=28)
pool1 (2×2):            6@28×28 → 6@14×14
conv2 (6→16, k5):       6@14×14 → 16@10×10   (14−5+1=10)
pool2 (2×2):            16@10×10 → 16@5×5
flatten:               16×5×5 = 400
fc1: 400 → 120 (ReLU)
fc2: 120 → 84  (ReLU)
fc3: 84 → 10   (no activation — raw logits)
```
The flatten size (`16*5*5`) is *(channels)×(height)×(width)* from the previous layer. It must match `fc1`'s `in_features` exactly or PyTorch throws a shape error. `x.view(-1, 16*5*5)` reshapes the 3D feature block into a flat vector per sample (`-1` infers batch size).

---

## 4. The training loop (standard pattern)

```python
for epoch in range(N):
    for inputs, labels in trainloader:
        optimizer.zero_grad()          # clear previous gradients (they accumulate by default)
        outputs = net(inputs)          # forward pass
        loss = criterion(outputs, labels)
        loss.backward()                # backprop: compute gradients
        optimizer.step()               # update weights
```
Then evaluate under `torch.no_grad()` with `net.eval()` (and `net.train()` afterward) to disable gradient tracking and switch layers like dropout/batchnorm to eval mode.

### Loss functions
- `nn.CrossEntropyLoss` — multi-class; applies log-softmax **internally**, so feed it **raw logits** (no softmax in the model).
- `F.binary_cross_entropy` — binary; requires inputs already in `[0,1]`, hence a **sigmoid** output layer.

### Prediction / thresholding
- After sigmoid (range `[0,1]`): threshold at **0.5** to pick a class.
- After tanh (range `[-1,1]`): threshold at **0**.
- The threshold is the activation's natural midpoint — using the wrong one misclassifies almost everything.

---

## 5. Hyperparameters & training behavior

### Learning rate
- Too low → very slow learning; may never converge within the epoch budget. (With momentum, progress can accelerate late as momentum builds.)
- A 10× increase (e.g. 0.0001 → 0.001) can be the difference between crawling to ~78% and smoothly reaching ~97%+.

### Convergence
- "Converged" = settled into a stable, good solution where loss stops meaningfully decreasing.
- A strict operational definition: 100% accuracy **sustained for N consecutive epochs** (not just hit once) — the "sustained" part confirms the solution is stable, not a lucky single epoch.

### Local minima
- The loss landscape has "valleys." Training can get stuck in a shallow one (a local minimum) that isn't the best solution — loss plateaus, accuracy stalls below target.
- Because weights are **randomly initialized** each run, re-running the same config can land in a different starting spot and converge where a previous run got stuck.
- **Consequence:** identical architecture + hyperparameters can converge at very different epoch counts across runs, or converge in some runs and not others. This is expected, not a bug.

### Capacity (network size)
- Too few hidden units → insufficient capacity; plateaus well short of the target no matter how long it trains.
- More units generally smooths the loss landscape (fewer/shallower traps) and converges more reliably — but the goal is often to find a value *close to the minimum* that still trains successfully.
- A size right at the minimum tends to converge slowly and unreliably (close to the epoch cap); a bit more capacity gives comfortable headroom and faster convergence.

---

## 6. Counting independent parameters

An **independent parameter** = one individually-learnable weight or bias, free to vary independently of all others (not derived from or tied to another).

### Per layer
```
nn.Linear(in, out):  weights = in × out,  biases = out   → total = in×out + out
nn.Conv2d(in, out, k): weights = (k×k×in) × out,  biases = out  → total = (k*k*in + 1) * out
```
- **Biases = `out`** because every output node gets its own bias.
- `bias=False` removes the bias term entirely (`y = xAᵀ`, weights still fully learned).
- The **input "layer" has zero parameters** — it's just data, not a computing layer. Input size only appears as the first layer's `in_features`.

### Whole network (any depth)
Sum `(inᵢ × outᵢ + outᵢ)` over every layer.

### Example totals (2 inputs, 1 output, `h` hidden units each layer)
- **3-layer FC** (2 hidden): `h² + 5h + 1`
- **4-layer FC** (3 hidden): `2h² + 6h + 1`
- Adding one hidden-to-hidden layer adds a full `h×h` weight matrix + `h` biases — the `h²` term dominates growth.

---

## 7. Fully connected vs. densely connected (shortcut connections)

- **Fully connected:** every node connects to every node in the *next* layer only; data flows strictly sequentially (input → h1 → h2 → out).
- **Densely connected:** adds **shortcut connections** that skip ahead — earlier layers (and the input) also feed *directly* into later layers.
- Note: in general ML usage "dense layer" and "fully connected layer" are synonyms; the "shortcut" meaning is specific to named DenseNet-style architectures.

### Implementing shortcut equations with `nn.Linear`
When several weighted sums feed one output but the equation has only **one** bias:
- Use a separate `nn.Linear` for each distinct source→destination weight matrix.
- Set `bias=False` on all but one of the layers feeding that output — otherwise you get multiple bias terms where the spec has one.
- **Why one bias:** a sum of biases is itself just a single constant (`b_A + b_B = b`), so extra biases add no representational power — they're redundant and would inflate the parameter count beyond the specification.
- Add the layer outputs with `+` inside `forward()`, then apply the activation.

Example (output receiving input, h1, h2, with one bias):
```python
out = torch.sigmoid(
    self.in_out(x)              # keeps bias  → the single b_out
    + self.h1_out(self.hid1)    # bias=False
    + self.h2_out(self.hid2)    # bias=False
)
```

### Why shortcuts help
A densely-connected layer receives both the **raw input** (via a shortcut) and the **already-transformed** output of an earlier layer at once. This lets a single layer combine a coarse linear split with finer non-linear detail — reaching complexity that a purely sequential network only achieves one layer deeper. Skip connections also let information/gradients flow directly across stages.

---

## 8. What each layer computes (interpreting decision boundaries)

Reasoning that generalizes to interpreting any layered network's learned functions:

- **Layer 1** (sees raw inputs only): each neuron's pre-activation is a **linear** function of the inputs, so its decision boundary is a **straight line**. Different neurons produce lines at different angles/positions.
- **Deeper layers:** each neuron combines the previous layer's outputs, which are **already non-linear** (tanh has been applied). A weighted combination of non-linear functions is itself non-linear → boundaries become **curved, then fragmented**, growing more complex with depth.
- **Output layer:** composes all the prior pieces into the final decision boundary, which approximates the true target pattern (fine detail where training data exists, coarser extrapolation elsewhere).

### Role of the activation function (tanh example)
- Splitting is linear because the **pre-activation** (`w1·x + w2·y + b`) is linear — a straight line where it crosses zero.
- Because tanh is **monotonic and passes through zero** (`tanh(0)=0`), it preserves *where* that boundary sits — it doesn't move or bend it.
- Separately, tanh **saturates** toward ±1 away from the boundary, turning a smooth unbounded surface into two flat plateaus — this is why thresholded plots show sharp, solid regions rather than gradients.
- The boundary's *position* is set by the learned weights/bias, so it need not pass through the coordinate origin — `tanh(0)=0` is about the tanh input being 0, not about the `(0,0)` point in coordinate space.
- **Non-monotonic** activations would break the single clean split (a value could cross the threshold multiple times → multiple boundary lines).

### Depth vs. output complexity
More layers/parameters increase the complexity of *intermediate* representations, but this doesn't always translate into a dramatically more complex *final output* — two networks of different depth can converge to broadly similar output functions, differing mainly in regions without training data (where nothing constrains the extrapolation).

---

## 9. Reading equation notation → code

For an equation of the form `activation( bias + Σ (weights × inputs) + ... )`:
- Each **Σ term** (one weighted sum from one source) = one `nn.Linear`.
- Weight labels like `w²¹` are compound "destination-source" tags (layer 2 ← layer 1), not the number 21.
- Subscripts (`h2ᵢ`) index *which neuron* in a layer; the equation is a general form applied to every neuron simultaneously by one `nn.Linear` with `out_features = hid`.
- The `+` between Σ terms in the equation = `+` between `nn.Linear` outputs in `forward()`.

---

## 10. Practical setup / environment notes

- On Windows, the command is usually `python`, not `python3` (the latter may trigger a Microsoft Store redirect).
- CLI-style training scripts (using `argparse`) run from a terminal, not inside a notebook. Small FC/CNN toy problems run fine on **CPU** — no GPU needed.
- If `conda install` stalls on solving the environment or hits solver errors, `pip install` usually resolves faster (it doesn't solve against the whole environment).
- SSL "self-signed certificate in certificate chain" errors on `pip install` are often caused by antivirus HTTPS scanning intercepting traffic — disable that feature or use `--trusted-host pypi.org --trusted-host files.pythonhosted.org`.
- `OMP: Error #15` (duplicate OpenMP runtime) can be worked around with `KMP_DUPLICATE_LIB_OK=TRUE` for small scripts.
- `pip`/`conda` install into whichever environment is currently active (shown in the prompt, e.g. `(base)`).
