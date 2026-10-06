# Design — what "good" means here

Applies to everything Kevin looks at on screen: pages, interfaces, output.
The house style governs how we write — this is how it has to look.

## Judge by the image

Take a screenshot and look at it. The code tells you what you meant; the
image tells you what came out.

**If you wouldn't show it yourself, it's not done.** "All values are correct"
is not a verdict: 17:1 contrast on an ugly page makes an ugly page with good
contrast.

## Two passes, at least

Build → look → revise. Whoever delivers after the first pass hasn't looked.
In the second pass you're not hunting bugs, you're answering one question:
**Would I show this to someone whose judgment I care about?**

## Reference means looking

If the task says "should look like X", open X and look at it. Copying color
values from a file isn't design — the feel lives in spacing, density,
typography and motion, not in `#00ff41`. Put your result and the reference
side by side before you deliver.

## Nothing sits on top of the content

Effects go **behind**: background, gradient, pattern, rain. None of it may sit
on top of text or images, and none of it may cost readability. An effect that
makes text harder to read isn't an effect, it's a bug. Everything that moves
can be switched off and respects `prefers-reduced-motion`.

## The empty state is a state

If an image is missing, **something takes its place**: typography, an
initial, a pattern with the title. Never an empty area — empty boxes don't
look minimalist, they look broken.

If the whole list is empty, the best thing in that spot is usually **the shape
of the entry that goes here**: the row as hinted bars, with a dashed outline,
a sentence below it and the one button. That explains without text what the
page can do. A big icon doesn't — when in doubt it looks like a glyph the
machine can't render.

Check every view in three cases, always:

- **no entries** — does the page say kindly that there's nothing here yet?
- **one entry** — does it then look empty and lost?
- **twenty entries** — does it get cluttered, do you have to scroll forever?

A view that only works with exactly six entries isn't done.

## The medium determines the presentation

Not everything is a tile with an image.

- **Music** is a list: title, duration, play button. A song without an image
  doesn't need an image, it needs a button.
- **Images** want space and little frame. Never crop through the middle of
  the subject or through text.
- **Text** wants line length — about 70 characters, not the full window width.
- **Code and paths** want monospace and wrapping, no ellipsis.

Whoever squeezes everything into the same tile hasn't understood the thing.

## Borders only where you click

A box around a piece of information looks like a control. In a list with
twenty entries, pretty tag chips turn into forty grey rectangles, and the list
flickers. The same information gets a border when it's a **control** (filter,
button) — and none when it just sits there. It costs nothing and calms a view
more than any color correction.

## Narrow means stacked, not smaller

At 375 px every line counts. Two notice bars on top of each other take a quarter
of the screen there: **one** strip shows the most important notice and counts
the rest (+2). What gets truncated is the title, never the reason — on narrow
screens the reason gets its own line. And whatever is wider than the screen
(org chart, tree) is not swiped but stacked: a spine on the left with the
entries hanging off it. Swiping hides half of it without saying so.

## Too little material is a finding

Don't invent content — but don't deliver a desert of placeholders either. If
there isn't enough material for a section, tell Kevin instead of putting up
three empty tiles. Three good entries beat ten half ones.

## Measuring comes last

Mandatory, not optional: contrast at least 4.5:1 for text and 3:1 for
controls, a visible focus ring on everything interactive, everything reachable
by keyboard, no horizontal scrolling at 320 px width, images with `alt`.

Measure on the running result in the browser, not on the variables in the
source. And measurements don't replace judgment — they're the floor.

**A border color is not a text color.** 3:1 is enough for outlines, not for
text — whoever uses the same grey for both has half their labels below the
threshold. That calls for its own step in the tokens: the quietest color that
may still be **text**.
