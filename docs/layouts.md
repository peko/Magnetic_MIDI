# Note layouts: the home-row "thirds" layout

`magmidi.midi` uses the **thirds** layout by default (`tools/magmidi/layouts.py`). The previous piano-style map,
where the bottom row holds the white keys and the row above the black keys, is still available as `--layout piano`.
This note explains why the thirds layout is built the way it is and how to play it.

## The problem with the piano projection

On a computer keyboard a piano projection puts the notes where a piano has them, not where the hands rest. On the
home row, the most practised and best-sensed position, nothing musically special happens. Every key (tonality) also
has a different fingering, so a C-major gesture does not transfer to D major. The piano is not isomorphic: the same
interval or chord takes a different shape depending on where it starts. On a grid of identical keys that only adds
difficulty and gives nothing back.

## Design goals

1. **Home row = home key.** The tonic chord lies under the resting fingers, and the tonic note sits on the tactile
   bump (J).
2. **Chords are the default gesture.** Pressing fingers that lie next to each other should sound a consonant chord.
   Tonal harmony is *tertian* (chords are stacks of thirds), so neighbouring keys should be a third apart.
3. **Shapes encode function, not pitch.** The layout is defined in **scale degrees**. Changing the tonic (arrows) or
   the mode (`--scale`) moves the music but not the fingers: I–IV–V is the same hand motion in every key. This is
   the "in-key" idea of Ableton Push/Move and the aQWERTYon.
4. **Two hands, two octaves.** The left hand plays an octave below the right, as on a piano, and both hands use
   identical shapes, so skills transfer from one hand to the other.

## Construction

Each hand works on its own block of the letter rows. The left hand has columns Q/A/Z to T/G/B; the right hand
has Y/H/N rightwards. Degrees are counted from the hand's tonic key: **S** for the left hand (ring finger) and **J**
for the right (index finger, on the bump).

| row | rule | left hand | right hand |
|---|---|---|---|
| home | every key is a **third** (2 scale steps) above its left neighbour | A S D F G | H J K L ; ' |
| bottom | sits *between* two home keys (QWERTY stagger) and gets the degree between them | Z X C V B | N M , . / |
| upper | the home key below it, **+1 octave** (7 degrees) | Q W E R T | Y U I O P [ ] |

As a formula, with home column `c` and tonic column `a`:
- home key: degree `2(c−a)`
- bottom key in column `c`: degree `2(c−a)+1`
- upper key in column `c`: degree `2(c−a)+7`

A degree `d` becomes a pitch through `12·⌊d/7⌋ + scale[d mod 7]`. The right hand adds 12, and `base_note` (48 = C3)
anchors everything.

C major:
```
 upper: Q  W  E  R  T      Y  U  I  O  P  [  ]
        A3 C4 E4 G4 B4     A4 C5 E5 G5 B5 D6 F6
 home:  A  S  D  F  G      H  J  K  L  ;  '
        A2 C3 E3 G3 B3     A3 C4 E4 G4 B4 D5
 bottom: Z  X  C  V  B      N  M  ,  .  /
         B2 D3 F3 A3 C4     B3 D4 F4 A4 C5
```

The home row is a slice of the **diatonic chain of thirds**: … la do mi sol si re fa …. All seven scale notes form
one such chain, and in it every three consecutive notes make a diatonic triad. The bottom row is the same chain
shifted by one step: si re fa la do mi. Between them, the two rows contain every scale degree.

## Properties

### Chords are windows

Any **3 adjacent keys in one row form a triad** of the scale, built on the leftmost key. **4 adjacent keys form a
seventh chord**, and 5 a ninth chord.

| keys (right / left) | notes | chord in C major |
|---|---|---|
| J K L / S D F | C E G | **I** (tonic, under the resting fingers) |
| H J K / A S D | A C E | vi |
| K L ; / D F G | E G B | iii |
| L ; ' / — | G B D | **V** |
| M , . / X C V | D F A | ii |
| , . / / C V B | F A C | **IV** |
| N M , / Z X C | B D F | vii° |
| J K L ; / S D F G | C E G B | Imaj7 |
| H J K L / A S D F | A C E G | vi7 (= C6) |

The three primary chords are each a single gesture. I is home, IV is the same three fingers dropped to the bottom
row half a key to the right, and V is the right-hand home row moved two keys to the right. The left hand has no root-position V, because its home row
ends on B3. It plays V as a second inversion, X F G (D G B), or plays just the bass note while the right hand plays
the chord.

The chord *quality* comes from the scale, not from the shape. In `--scale minor` the same J K L gives C E♭ G (i), and
H J K gives A♭ C E♭ (VI). The shape names the **function** of the chord: tonic, subdominant, and so on.

### Steps live on the diagonals (voice leading)

Each bottom key sits between two home keys, so every home key has two diagonal neighbours below it:

- **down-right = one scale step up** (K E4 → , F4)
- **down-left = one scale step down** (K E4 → M D4)

A scale therefore runs as a zigzag between the rows: J M K , L . ; / gives C D E F G A B C. Stepwise voice leading,
the basis of smooth chord changes, is a finger rocking to the neighbouring row. Common tones stay where they are.
The textbook progression I – IV⁶₄ – V⁶ – I is one example:

```
I      J K L   C E G
IV⁶₄   J , .   C F A    K→, and L→. move down-right (each voice one step up); J holds C
V⁶     N M L   B D G    J→N and K→M move down-left (each voice one step down); L holds G
I      J K L   C E G
```

The hand never leaves its position. A piano needs a separate fingering for this progression in each key; here it
is the same in all 12 keys and in every mode.

### Intervals by geometry

| interval | gesture |
|---|---|
| step (2nd) | diagonal to the bottom row |
| third | next key in the same row |
| fifth | skip one key in the same row (J → L) |
| octave | the key in the row above (S C3 → W C4, J C4 → U C5) |
| octave between hands | the same finger position in the other hand (S C3 ↔ J C4) |

Arpeggios (thirds) are the easiest melodic figure, and scales (steps) are a zigzag. That is the opposite trade-off
from the piano, and it suits a keyboard whose strength is chords under resting fingers.

### Stable notes are where the fingers rest

The resting positions are left A S D F (A C E G) and right J K L ; (C E G B). They hold mostly the tonic chord tones
1, 3 and 5, the notes a melody comes to rest on. The tension and passing tones 2, 4 and 6 lie mainly on the bottom
row, one diagonal away. With `--light`, keys are coloured by degree, so the colours stay correct after transposition:
- tonic: orange
- 3rd and 5th: white
- other degrees: blue

## Controls that complete the layout

- **Arrows: transpose by a semitone**, **Shift+arrows: transpose by an octave.** Only the tonic changes; every shape
  above stays the same.
- **LAlt / RAlt held: the left / right hand's notes go up a semitone** (accidentals; there are no flats, so B♭ is
  A♯). This gives secondary dominants and other chromatic chords. For example, V/V in C is D F♯ A: play X and V, then add C with LAlt held.
  The pitch is fixed at note-on, so releasing Alt does not bend a held note.
- **Space: sustain pedal, inverted.** The pedal is down while Space is up, so released notes ring on. Pressing
  Space damps them.
- `--scale major | minor | dorian | mixolydian | harmonic_minor` changes which chord qualities the shapes produce.

## Ranges and overlaps

- **Left hand:** A2 to B4 with its upper row; home and bottom rows A2 to C4.
- **Right hand:** A3 to F6 (home and bottom rows A3 to D5).
- **Overlaps:** the hands share notes where they meet (left B = C4 = right J; left V = A3 = right H; the left
  upper row = right home row). The duplicates give alternative fingerings and let either hand take over a line.

## Limitations

- **Fast scale runs are slower** than in a five-finger piano position, because every step changes row.
- **Diatonic only.** Chromatic lines need the Alt modifiers. The layout preserves scale-degree intervals, not exact
  semitone intervals, so it is "isomorphic" in the diatonic sense (like Push In-Key), not chromatically like
  Wicki–Hayden or the harmonic table.
- **Each hand window is about 1¼–1½ octaves** on the home and bottom rows. The upper row adds an octave, but only as
  the doubling of the home row.
- **The left hand has no root-position V** (see above).

## Lineage and related work

- **Tonnetz and harmonic table:** triads as adjacent notes, a chromatic 2-D lattice of thirds and fifths. The thirds
  layout is its diatonic, row-wise projection.
  [Harmonic table](https://en.wikipedia.org/wiki/Harmonic_table_note_layout),
  [Interactive Tonnetz](https://ohotnik.duckdns.org/codedot/tonnetz),
  [TonnetzViz](https://cifkao.github.io/tonnetz-viz).
- **aQWERTYon (NYU MusEDLab):** in-key QWERTY with rows as the scale and columns as chords. The thirds layout swaps
  the axes: rows are chords and the diagonals are the scale.
  [Inside the aQWERTYon](https://ethanhein.substack.com/p/inside-the-aqwertyon).
- **Ableton Push/Move In-Key mode:** only scale notes, and shapes that transpose unchanged.
  [Move 4ths layout](https://isotonikstudios.com/ableton-move-1-4-update-play-like-a-pro-with-the-new-4ths-layout/).
- **Wicki–Hayden, Relayer:** chromatic isomorphic layouts on QWERTY.
  [Wicki–Hayden](https://en.wikipedia.org/wiki/Wicki%E2%80%93Hayden_note_layout),
  [Relayer](https://www.dynamictonality.com/relayer.htm).
- **Stradella bass (accordion):** one button per chord, ordered by the circle of fifths. The thirds layout keeps
  single-note keys, so voicings and inversions stay free.
  [Stradella bass system](https://en.wikipedia.org/wiki/Stradella_bass_system).
- **Kalimba:** consecutive scale steps alternate sides, the same alternation the thirds layout uses between rows.
  [Kalimba Magic](https://www.kalimbamagic.com/?p=791).
- **US patent 6444888:** puts the most frequently used notes on the home row.
  [US6444888](https://patents.google.com/patent/US6444888).

## Seeing it

`magmidi.midi --tui` shows the computer keyboard with each key's current note, and a piano under it. On the piano,
held notes are lit, notes ringing on the pedal are shaded, and every piano key is labelled with the computer key(s)
that play it at the current transposition. Run it in a real terminal (about 110 columns):

```sh
PYTHONPATH=tools .venv/bin/python -m magmidi.midi --tui --to FLUID
```
