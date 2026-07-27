#!/usr/bin/env python3

__all__ = ['plot', 'caption', 'document', 'itemgrid', 'tags', 'util', 'slider', 'sliderlock', 'dropdown']

from dominate import tags, document, util
from io import BytesIO
import imageio
import base64
import tempfile
from pathlib import Path

class document(document):
    def save(self, out):
        """Convenience function save to disk

        Args:
            out (str, Path, or stream): location to write document to

        Returns:
            None or file
        """
        if hasattr(out, "write"):
            out.write(self.render())
        elif type(out) in (str, Path):
            f = open(out, 'w')
            f.write(self.render())
            return f


class plot(tags.img):
    """Create HTML plot from Matplotlib figure/anim

    Args:
        content (Figure, Animation, or str): Generate image or animation
            if given a matplotlib Figure or Animation.  Use `content` as
            <img> src if given str.  Omit to use as context manager.
        format (str): format to use when saving matplotlib Figure/Animation
        matkwargs: extra matplotlib arguments
        **kwargs: extra dominate arguments
    """

    tagname = 'img'

    def __init__(self, content=None, format=None, matkwargs={}, **kwargs):
        import matplotlib, matplotlib.animation

        self.format = format
        self.matkwargs = matkwargs

        content = content.figure if hasattr(content, 'figure') else content

        if content is None:
            src = ''
        elif isinstance(content, str):
            src = content
        elif isinstance(content, matplotlib.figure.Figure):
            src = self._to_img(content, format, matkwargs)
        elif isinstance(content, matplotlib.animation.Animation):
            fmt = 'gif' if format is None else format
            with tempfile.NamedTemporaryFile(suffix=f'.{fmt}', delete=True) as tmpfile:
                content.save(tmpfile.name, **matkwargs)
                tmpfile.seek(0)
                src = f'data:image/{fmt};base64,{base64.b64encode(tmpfile.read()).decode()}'
        else:
            raise TypeError(f"Unsupported object {type(content)}")

        super().__init__(src=src, **kwargs)

    @staticmethod
    def _to_img(fig, format, matkwargs):
        import numpy as np
        fmt = 'png' if format is None else format
        buff = BytesIO()
        with np.errstate(under='ignore'):
            fig.savefig(buff, format=fmt, **matkwargs)
        return f'data:image/{fmt};base64,{base64.b64encode(buff.getvalue()).decode()}'

    def __enter__(self):
        import matplotlib.pyplot as plt
        self._fig = plt.figure()
        return super().__enter__()

    def __exit__(self, *args):
        import matplotlib.pyplot as plt
        self['src'] = self._to_img(self._fig, self.format, self.matkwargs)
        plt.close(self._fig)
        return super().__exit__(*args)


class caption(tags.figure):
    """Wraps a set of elements in a <figure> w/ <figcaption>

    Args:
        title (str): title to put in figcaption
        *args (list[...]): list of items to put in figure
        flow (str): flex direction for content ('row' or 'column')
    """

    tagname = 'figure'

    def __init__(self, title, *args, flow='row', **kwargs):
        kwargs['style'] = f"""
        display: inline-flex;
        flex-direction: {flow};
        border: 1px solid black;
        """ + kwargs.get('style', "")
        self._inner = tags.div(*args, **kwargs)
        super().__init__(
            tags.figcaption(title),
            self._inner,
            style="margin:5pt;"
        )

    def __enter__(self):
        super().__enter__()
        return self._inner.__enter__()

    def __exit__(self, *args):
        self._inner.__exit__(*args)
        return super().__exit__(*args)


class itemgrid(tags.div):
    """Create a CSS grid of items

    Args:
        length (int): number of items per col/row
        *args: arguments to pass to underlying `dominate.div` tag
        flow (str): flow items as either 'row' or 'col' first
        **kwargs: kwargs to pass to underyling `dominate.div` tag
    """

    def __init__(self, length, *args, flow='row', **kwargs):

        if flow == 'row':
            grid_template = f'grid-template-columns: {"min-content " * length}'
        elif flow == 'column':
            grid_template = f'grid-template-rows: {"min-content " * length}'
        else:
            raise ValueError(f"Invalid value for `flow` {flow}")

        kwargs['style'] = f"""
        display: grid;
        {grid_template};
        grid-auto-flow: {flow};
        """ + kwargs.get('style', "")

        super().__init__(*args, **kwargs)

SLIDER_SCRIPT = r'''
// make scope of entire script private
(() => {
var s = document.currentScript;
document.addEventListener('DOMContentLoaded', () => {
// --- get HTML elements ---
var c = s.parentNode.parentNode;
var range = c.querySelector(".slider-range")
var counter = c.querySelector(".slider-counter")
var playpause = c.querySelector(".slider-playpause")
// get slider items, exclude controls div
var items = Array.from(c.children).filter(el => !el.classList.contains('slider'))
var labels = items.map((el, i) => el.getAttribute('label') ?? LABELINSERT[i] ?? String(i))
range.max = items.length - 1

// hide all items, saving original display value for restore
for (const item of items) {
    item._display = getComputedStyle(item).display;
    item.style.display = 'none';
}

// --- state ---
var current = null
var playing = false
// timer runs unconditionally; ticks are suppressed when paused or driven
window.setInterval(tick, INTERVAL)

// show item `index`, hiding the previous one
function show(index, propagate=true) {
    index = Math.min(Math.max(index, 0), items.length - 1)
    range.value = index
    counter.innerHTML = labels[index]
    var next = items[index]
    // make sure to load next image before hiding current to prevent flashing
    var img = next.matches('img') ? next : next.querySelector('img')
    var ready = img ? img.decode().catch(() => {}) : Promise.resolve()
    ready.then(() => {
        if (current) current.style.display = 'none'
        current = next
        current.style.display = current._display
    })
    if (propagate) peers().forEach(o => o.show(index, false))
}

function setPlaying(state, propagate=true) {
    playing = state
    playpause.innerHTML = playing ? '⏸' : '⏵'
    if (propagate) peers().forEach(o => o.setPlaying(state, false))
}

function tick() {
    // while locked together, the first playing slider of the group drives
    // the rest, so that a group advances at a single rate
    var leads = o => o.playing && window.domrepSliders.indexOf(o) < order
    if (!playing || peers().some(leads)) return
    show((range.valueAsNumber + 1) % items.length)
}

// --- lock groups ---
// sliders/locks register in page-global lists.  peers are the sliders that
// some checked lock currently ties us to
function peers() {
    return window.domrepSliders.filter(o => o !== self && (window.domrepLocks || []).some(
        l => l.checked() && (l.group === null || (l.group === self.group && l.group === o.group))
    ))
}

var self = {
    group: GROUPINSERT,
    show: show,
    setPlaying: setPlaying,
    get playing() { return playing },
    // push our state onto everything we are now locked to
    sync: () => { show(range.valueAsNumber); setPlaying(playing) },
}
window.domrepSliders = window.domrepSliders || []
var order = window.domrepSliders.push(self) - 1

range.oninput = () => show(range.valueAsNumber)
playpause.onclick = () => setPlaying(!playing)
show(range.valueAsNumber)
setPlaying(false)
});
})();
'''

SLIDERLOCK_SCRIPT = r'''
(() => {
var s = document.currentScript;
document.addEventListener('DOMContentLoaded', () => {
var checkbox = s.parentNode.querySelector('input.sliderlock')
var group = GROUPINSERT
window.domrepLocks = window.domrepLocks || []
window.domrepLocks.push({group: group, checked: () => checkbox.checked})
// on locking, align the group to its first slider
checkbox.onchange = () => {
    var members = window.domrepSliders.filter(o => group === null || o.group === group)
    if (checkbox.checked && members.length) members[0].sync()
}
});
})();
'''


def _groupinsert(s, group):
    return s.replace('GROUPINSERT', 'null' if group is None else repr(str(group)))


def sliderlock(group=None, label=None, **kwargs):
    """Checkbox that locks sliders together: while checked, moving any
    slider in `group` moves all sliders in that group.

    Args:
        group (str, optional): slider group to lock; None locks all sliders
        label (str, optional): checkbox label text
    """
    if label is None:
        label = f'lock {group} sliders' if group else 'lock all sliders'
    return tags.div(
        tags.label(
            tags.input_(type="checkbox", _class="sliderlock"),
            label,
        ),
        tags.script(util.raw(_groupinsert(SLIDERLOCK_SCRIPT, group)), defer=True),
        **kwargs
    )

def slider(*args, labels=None, interval=300, group=None, **kwargs):
    """Create a sliding range of elements

    Args:
        *args: items to plot, may be `plot`s or any domrep object
        labels (list(str), optional): slider labels
        interval (int): time between frames (ms)
        group (str, optional): lock-group name, see `sliderlock`

    Labels may also be specified by `label` kwarg.  e.g:

        slider(
            plot(plt.imshow(...), label='foo 1'),
            ...
            plot(plt.imshow(...), label='foo 10'),
        )
    """
    if labels is None:
        labels = [f"{n}" for n in range(len(args))]
    elif type(labels) is str:
        labels = [f"{labels} {n}" for n in range(len(args))]
    # substitute arguments into Javascript
    s = SLIDER_SCRIPT.replace('INTERVAL', str(interval))
    s = s.replace('LABELINSERT', str(labels))
    s = _groupinsert(s, group)
    return tags.div(
        *args,
        tags.div(
            tags.label(_class="slider-counter"),
            tags.input_(_class="slider-range", type="range", max=len(args)-1, value="0"),
            tags.button("⏵", _class="slider-playpause"),
            tags.script(util.raw(s), defer=True),
            style="order: 1; display: flex; align-items: center; justify-content: center",
            _class="slider"
        ),
        style="display: inline-flex; flex-direction: column",
        **kwargs
    )


DROPDOWN_SCRIPT = r'''
(() => {
var s = document.currentScript;
document.addEventListener('DOMContentLoaded', () => {
var labels = LABELINSERT
var c = s.parentNode.parentNode;
var dropdown = c.querySelector("#dropdown")
// get items, exclude controls div
var items = Array.from(c.children).filter(el => !el.classList.contains('dropdown'))
labels = items.map((el, i) => el.getAttribute('label') ?? labels[i] ?? String(i))

// populate dropdown options
for ([index, label] of labels.entries()) {
    var opt = document.createElement('option')
    opt.value = index
    opt.innerHTML = label
    dropdown.appendChild(opt)
}

// hide all items, saving original display value for restore
for ([index, item] of items.entries()) {
    item._display = getComputedStyle(item).display;
    item.style.display = 'none';
}

// show selected item on change
var current = null;
dropdown.onchange = function() {
    if (current) current.style.display = 'none';
    current = items[this.value];
    current.style.display = current._display;
}
dropdown.onchange()
});
})();
'''

def dropdown(*args, labels=None, **kwargs):
    """Create a dropdown selector for a set of elements

    Args:
        *args: items to show, may be `plot`s or any domrep object
        labels (list(str), optional): dropdown option labels

    Labels may also be specified by `label` kwarg on each item.
    """
    if labels is None:
        labels = [f"{n}" for n in range(len(args))]
    elif type(labels) is str:
        labels = [f"{labels} {n}" for n in range(len(args))]
    s = DROPDOWN_SCRIPT.replace('LABELINSERT', str(labels))
    return tags.div(
        *args,
        tags.div(
            tags.select(id="dropdown"),
            tags.script(util.raw(s), defer=True),
            style="order: 1; display: flex; align-items: center; justify-content: center",
            _class="dropdown"
        ),
        style="display: inline-flex; flex-direction: column",
        **kwargs
    )


if __name__ == '__main__':
    import matplotlib.pyplot as plt
    import matplotlib
    import numpy as np
    matplotlib.use('Agg')

    with document('hello new') as d:
        with itemgrid(3, flow='column'):
            for a in range(3):
                for b in range(3):
                    fig, ax = plt.subplots()
                    ax.imshow(np.random.random((50, 50)))
                    fig.tight_layout()
                    caption("hello", plot(fig))
    open('/www/dom.html', 'w').write(d.render())

    with document('hello') as d:
        with caption('testing'):
            slider(*[plot(plt.imshow(x)) for x in np.random.random((20, 50, 50))])

    open('/www/dom2.html', 'w').write(d.render())

    with document('hello') as doc:
        with slider():
            for x in np.random.random((20, 50, 50)):
                plot(plt.imshow(x))

    open('/www/dom22.html', 'w').write(doc.render())

    with document('title') as doc:
        plots = []
        for x in range(10):
            plots.append(plot(plt.imshow(np.random.random((10, 10)))))
        slider(*plots, interval=50)

    open("/www/dom3.html", "w").write(doc.render())

    with document('title') as doc:
        plots = []
        with slider(interval=50):
            for x in range(10):
                plot(plt.imshow(np.random.random((10, 10))))

    open("/www/dom4.html", "w").write(doc.render())