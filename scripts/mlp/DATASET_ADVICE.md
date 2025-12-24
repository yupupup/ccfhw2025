# Dataset Generation Advice for V8 Tuning

## 1. Feasibility of JetStream 2 in `d8`

### Can JetStream 2 run in `d8`?
**Partially.** JetStream 2 is designed as a **browser benchmark**. It measures not just raw JavaScript execution speed but also the interaction with Web APIs, DOM, and WebAssembly.
*   **Pure JS/Wasm kernels**: Many sub-benchmarks (like those from Octane, SunSpider, Kraken) are computational kernels and **can** be run in `d8` with some wrapper scripts.
*   **Browser-specific tests**: Some tests rely on the DOM or specific browser APIs and **cannot** run in `d8` directly.

### Recommendation
1.  **Use Subsets**: Extract the pure JavaScript/Wasm kernels (e.g., Octane, SunSpider) from JetStream 2. These are standard for V8 `d8` tuning.
2.  **Headless Browser**: If you *must* use the full JetStream 2 suite, you cannot use `d8`. You must use a headless browser (e.g., Chrome controlled via Puppeteer/Selenium).
    *   *Pros*: Accurate representation of real-world browser performance.
    *   *Cons*: **Much slower** execution (10x-100x slower than `d8`). This will severely limit your data generation speed.

**Verdict**: For training a V8 flag tuner, **`d8` with Octane/SunSpider** is the standard and recommended approach due to speed.

## 2. Dataset Size & Quality

### Is 6,400 samples (64 benchmarks * 100 rounds) enough?
**No, it is likely too small.**
*   **High Dimensionality**: You have 15+ parameters. The state space is huge.
*   **Complex Landscape**: Performance is non-linear. 100 samples per benchmark is barely enough to find a local optimum, let alone learn the global landscape for a predictive model.
*   **Overfitting Risk**: With only 6,400 samples, a neural network (even a small MLP) will likely memorize the data rather than learn generalizable features.

### Recommendation
Aim for **at least 50,000 samples**.
*   If using `d8` (fast): You can easily generate 100k+ samples.
*   If using Headless Browser (slow): You might be limited to 10k-20k, in which case you should use a simpler model (e.g., Random Forest/XGBoost) instead of an MLP.

## 3. Sampling Strategy: OpenTuner vs. Random

### The Problem with "Only OpenTuner"
OpenTuner is an **optimization** engine. It is designed to find the *best* configurations.
*   **Bias**: Your dataset will be heavily skewed towards "Good" and "Excellent" configurations.
*   **Blind Spots**: The model will never see "Bad" or "Average" configurations.
*   **Consequence**: The model might predict *everything* is "Good", or fail to recognize when a parameter change causes a performance regression.

### Recommended Hybrid Strategy
Construct your dataset with a mix of strategies:
1.  **Exploration (40%)**: Use **Latin Hypercube Sampling (LHS)** or Uniform Random Sampling.
    *   *Goal*: Cover the entire parameter space evenly. Learn what "average" and "bad" look like.
2.  **Exploitation (40%)**: Use **OpenTuner** traces.
    *   *Goal*: Provide dense data around the high-performance regions.
3.  **Boundary Testing (20%)**: Specifically sample near the default values (0.5x to 2.0x).
    *   *Goal*: Ensure high accuracy for the most common use cases.

## 4. Summary Action Plan

1.  **Environment**: Switch to using **Octane** or **SunSpider** benchmarks running in `d8` for speed.
2.  **Data Generation**:
    *   Run 500 rounds of Random/LHS sampling per benchmark.
    *   Run 500 rounds of OpenTuner per benchmark.
    *   Total: 64 benchmarks * 1000 rounds = **64,000 samples**.
3.  **Feature Engineering**: Ensure you capture code features (AST stats) for each benchmark to help the model distinguish between them.
