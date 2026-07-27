# domrep — agent guide

Generate self-contained HTML reports from Python. Thin layer over
[dominate](https://github.com/Knio/dominate): everything is a dominate tag, so
`tags.h1(...)`, `tags.pre(...)`, `tags.a(href=...)` etc. all work and nest via
`with` blocks. Images are embedded as base64 data URIs — the output is a single
file with no external assets.

```python
from domrep import *   # plot, caption, document, itemgrid, slider, sliderlock, dropdown, tags, util
```

Use `matplotlib.use('Agg')` before importing pyplot in report scripts.

## Core idea

Inside a `with` block, any element you construct is appended to the enclosing
element. So you never assign to variables unless you want to — just construct.

```python
with document('My Report') as doc:
    tags.h1('Section')
    with caption('A random array'):
        plot(plt.imshow(random((100, 100))))
doc.save('output.html')      # or: Path(...).write_text(doc.render())
```

## API

### `plot(content=None, format=None, matkwargs={}, **kwargs)`
`<img>` from a matplotlib `Figure`, `Animation` (→ gif), an object with a
`.figure` attribute (e.g. the return of `plt.imshow`/`ax.imshow`), or a `str`
src. `matkwargs` go to `savefig`/`Animation.save`; other kwargs are HTML attrs
(`width=720`, `height=350`, `label='Date 3'`).

```python
plot(fig, width=720)
plot(plt.imshow(im))                      # pyplot handle works
plot(anim, matkwargs={'fps': 10})
with plot(label='Date 3'):                # ctx manager: draws into a fresh figure
    plt.imshow(im); plt.colorbar()
```

Reusable style dict is idiomatic: `figset = {'width': 720}` … `plot(fig, **figset)`.

### `caption(title, *args, flow='row')`
`<figure>` + `<figcaption>`. Works as call **or** context manager:

```python
caption('Two panels', plot(fig1), plot(fig2))
with caption('Two panels'):
    plot(fig1); plot(fig2)
```

### `itemgrid(length, *args, flow='row')`
CSS grid, `length` items per row (`flow='row'`) or per column
(`flow='column'`). Usually wraps the whole report body:
`with itemgrid(length=4): ...`

### `slider(*args, labels=None, interval=300, group=None)`
One visible child at a time, with a range input and ⏯ autoplay button
(`interval` ms). Call or context-manager form:

```python
slider(*[plot(f) for f in figs], labels=labels)
with slider(labels=labels, group='january'):
    for fig in figs:
        plot(fig)
```
Labels come from `labels=` (list, or a str prefix → `"foo 0"`, `"foo 1"`, …) or
per-item `label=` kwargs on the children (per-item wins).

### `sliderlock(group=None, label=None)`
Checkbox that ties sliders together — while checked, moving one slider moves
all others sharing the same `group` (`group=None` locks every slider on the
page). Place it once, before the sliders it governs.

### `dropdown(*args, labels=None)`
Same selection semantics as `slider`, rendered as a `<select>`. No autoplay/
no lock groups.

### `document(title)` / `doc.save(out)`
`document` subclasses `dominate.document`; `save` accepts a path (str/Path) or
any writable stream. `doc.render()` returns the HTML string.

## Report script skeleton

Pattern used by `carr/cross/cross_cal.py` and `carr/recon/recon_1D.py`:

```python
from domrep import *
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

with document('NFI/WFI Cross Calibration') as doc:
    figset = {'height': 350}

    for name, period in periods.items():
        tags.h1(f'{name}')
        sliderlock(group=name)             # lock the sliders in this section
        with itemgrid(length=4):
            plt.close('all')

            with caption('interpolated WFI / NFI'):
                with slider(labels=labels, group=name):
                    for im, label in zip(ims, labels):
                        fig, ax = plt.subplots()
                        h = ax.imshow(im, clim=(1, 2))
                        fig.colorbar(h, label='WFI / NFI')
                        ax.set_title(label)
                        plot(fig, **figset)
                        plt.close(fig)     # figures accumulate — close them

            with caption('median ratio vs date'):
                fig, ax = plt.subplots()
                ax.plot(dates, medians, 'o-')
                plot(fig, **figset)

    tags.h1('Source Code')                 # embed the script itself
    tags.code(tags.pre(open('cross_cal.py').read()))

outfile = Path('/www/cross/cross_cal.html')
outfile.parent.mkdir(parents=True, exist_ok=True)
outfile.write_text(doc.render())
print(f'Saved to {outfile}')
```

## Gotchas

- Each `plot` embeds a full base64 PNG. Long sliders make large files — keep
  figure `dpi`/size modest (`plt.subplots(figsize=(8, 4), dpi=150)`).
- Close figures (`plt.close(fig)` / `plt.close('all')`) inside loops or
  matplotlib warns and leaks memory.
- `caption`'s title is positional and required.
- Slider/dropdown scripts run on `DOMContentLoaded` and select siblings by
  class, so don't hand-wrap their output in extra divs.
- `slider` sizes itself to the first item; give same-shaped figures per slider.
