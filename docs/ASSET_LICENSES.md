# Visual assets and rights

ProofFlow's interface layout, CSS and product mark are maintained in this
repository. Third-party visual assets are identified below. No Duolingo
illustrations, mascots, logos or other Duolingo brand assets are included.

| Asset | Origin and version | License | Local files |
| --- | --- | --- | --- |
| Phosphor SVG icons, regular and duotone | Official npm package `@phosphor-icons/core`, version `2.1.1`; upstream [phosphor-icons/core](https://github.com/phosphor-icons/core) | MIT; copyright and permission notice retained | [`frontend/assets/icons/`](../frontend/assets/icons/) and [`LICENSE-phosphor.txt`](../frontend/assets/icons/LICENSE-phosphor.txt) |

The bundled subset contains 50 SVG files: 25 regular and 25 duotone variants.
The icon license permits use, modification and redistribution subject to
retaining the copyright and permission notice. The bundled license remains
the authoritative wording; this note does not replace it.

Icons are served locally. The workbench uses system fonts and does not require
an external font service or icon CDN at runtime. Source data, supplier product
names and imported partner files are not UI asset licenses and must not be
published as visual assets.

Python dependencies are listed separately in `requirements.lock` and retain
their respective upstream licenses. This asset notice does not relicense
those packages or claim ownership of third-party work.
