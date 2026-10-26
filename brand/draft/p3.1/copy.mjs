// Board copy per concept. Verdicts: "Pass" or "Note" (passes, with something P3.2 should look at) or "Misses".
const grid = (cuts) => ["Pass", "Solid blocks, 100-unit grid", `Every edge is on the grid except the cut ends (${cuts}), which follow from a one-stroke channel at 45°, as TecHaust's 73.13 does.`];
const width = ["Pass", "Channel exactly one stroke", "19 units square to the cut (26.87 across), equal to the vertical stroke. At 16 px it is 4 px across, 2.8 px square to the cut, as in TecHaust's favicon."];
const thin = ["Pass", "Horizontals about 8 % thinner", "17.5 against 19 (7.9 %) in the vector and 11 against 12 px at 64 px. At 32 and 16 px they are equal, the same pixel-fitting rule as TecHaust's."];
const dark = ["Pass", "Colour on dark", "Mist with verdigris-300: 13.4 and 7.9 to 1 on the ink-900 app bar, 13.5 and 7.9 to 1 on the dark taskbar mock."];

export const COPY = {
  "1-shelves": {
    idea: "An ink upright carries two shelves. The verdigris product is still sliding in on the middle shelf: its leading edge is cut at 45°, one stroke clear of the ink.",
    plate: "Vector, 100 units. Ink stub cut at 45.25, verdigris bar cut at 72.12; the shelves stop at 81 so the bar stands proud.",
    dimT: 0,
    strong: "the open bracket and the proud verdigris bar keep their shape at 16 px, and the mark looks like nothing else in the tray.",
    weak: "it reads first as a capital E (close to a euro sign at tray size), and the ink stub ahead of the channel is only 2 to 5 px wide at 16 px, so the cut reads as a small notch.",
    checks: [
      grid("45.25, 72.12"),
      ["Pass", "One decorative device", "One channel, in the middle bar. No other cut, curve or detail."],
      width,
      thin,
      ["Pass", "Ink base, verdigris accent", "Verdigris only on the product bar, the smallest share of the three concepts. 6.3 to 1 on white."],
      dark,
      ["Pass", "No sync clichés", "No arrows, circles, clouds or ticks. The upright keeps the three bars from reading as a menu icon."],
    ],
  },
  "2-s-cut": {
    idea: "An S from two offset blocks: the ink top half and the verdigris bottom half meet in the spine, split by the one-stroke channel, as the T and H share a channel in TecHaust's mark.",
    plate: "Vector, 100 units. The channel is centred on the spine: ink cut at 45.32, verdigris cut at 72.19, spine centred at 48.5.",
    dimT: 0,
    strong: "the closest relative of the TecHaust mark, and the letter gives the name; the two halves stay apart at every size.",
    weak: "a square S built from blocks can be taken for a 5, and in dark mist and verdigris-300 differ more in hue than in lightness (1.7 to 1), so the split between the halves leans on the 4 px gap.",
    checks: [
      grid("45.32, 72.19"),
      ["Pass", "One decorative device", "One channel, in the spine. The terminals are square."],
      width,
      thin,
      ["Note", "Ink base, verdigris accent", "Never swapped, but verdigris takes half the mark, more than the other two concepts and more than \"used sparingly\" suggests. 6.3 to 1 on white."],
      dark,
      ["Pass", "No sync clichés", "No arrows, circles, clouds or ticks. The channel runs across the spine, so there is no arrowhead."],
    ],
  },
  "3-one-to-many": {
    idea: "One ink block, the file, feeds two verdigris stems, the stores. A single 45° channel separates them; its far edge cuts the tops of both stems.",
    plate: "Vector, 100 units. Ink bar cut at 73.13 (TecHaust's own value); both stem tops lie on x + y = 100, stems at 40.5 and 81.",
    dimT: 4,
    strong: "one clean 45° line runs through the bar end and both stem tops, and it still reads as one line at 16 px; the idea of one file reaching every store is the most literal of the three.",
    weak: "at 16 px the two verdigris stems read as a rising bar chart, a stock stats icon; the middle stem's tip sits under open space, so the feeding needs explaining; and the top right corner is TecHaust's own construction.",
    checks: [
      grid("73.13"),
      ["Note", "One decorative device", "One channel, but it cuts two stem tops along its far edge: one line, two cut ends. P3.2 should rule whether that counts as one device."],
      width,
      thin,
      ["Pass", "Ink base, verdigris accent", "Ink carries the bar and the first stem; verdigris the two stores. 6.3 to 1 on white."],
      dark,
      ["Note", "No sync clichés", "No arrows, circles, clouds or ticks. Not a banned motif, but the two stepped verdigris stems recall a bar chart or signal-strength icon at small sizes."],
    ],
  },
};
