// Layout for Scrutineer_Report.pdf. The body is technical_report.md converted by pandoc.
#set document(title: "Scrutineer: multilingual recall of Swiss federal vote outcomes", author: "Tim (winsznx)")
#set page(paper: "a4", margin: (x: 1.45cm, top: 1.5cm, bottom: 1.6cm), numbering: "1",
  footer: context [
    #set text(size: 7pt, fill: rgb("#6b6b6b"))
    Scrutineer · Hack Apertus 2026, track 1B · CC-BY-4.0 #h(1fr) #counter(page).display()
  ])
#set text(font: "IBM Plex Sans", size: 8.4pt, lang: "en", fill: rgb("#1a1a1a"))
#set par(justify: true, leading: 0.52em, spacing: 0.75em)
#show raw: set text(font: "DejaVu Sans Mono", size: 7pt)
#show link: set text(fill: rgb("#1a1a1a"))
#show heading: set block(above: 1.0em, below: 0.5em)
#show heading.where(level: 1): set text(size: 15pt, weight: "semibold")
#show heading.where(level: 2): it => block(above: 1.1em, below: 0.45em)[
  #line(length: 100%, stroke: 0.5pt + rgb("#1a1a1a"))
  #v(-0.3em)
  #text(size: 9.6pt, weight: "semibold", it.body)
]
#show heading.where(level: 3): set text(size: 8.6pt, weight: "semibold")
#show heading.where(level: 4): set text(size: 8.4pt, weight: "semibold")
#set table(inset: (x: 2.5pt, y: 2pt), stroke: (x, y) => (
  top: if y == 0 { 0.6pt } else { 0pt },
  bottom: if y == 0 { 0.4pt } else { 0.2pt + rgb("#d9d9d6") },
))
#show table: set text(size: 6.4pt)
#show table: set par(justify: false)
#show figure: set block(breakable: false, above: 0.8em, below: 0.8em)
#show figure.caption: set text(size: 7pt, fill: rgb("#6b6b6b"))
#set figure(gap: 0.4em)
#let horizontalRule = line(length: 100%, stroke: 0.4pt + rgb("#d9d9d6"))
#let divider = horizontalRule
#show quote: it => block(inset: (left: 0pt), text(size: 9pt, it.body))

#columns(2, gutter: 0.55cm)[
#include "body.typ"
]
