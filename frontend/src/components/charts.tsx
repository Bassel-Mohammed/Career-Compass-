import { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { DemandBand } from '../types';
import { BAND_META } from '../pages/student/dashboard';

/**
 * The dashboard's charts.
 *
 * Recharts is confined to this file. Everywhere else in the app draws its own inline SVG, and
 * letting chart internals leak into page files is how a component library ends up owning a
 * layout it was never asked to own.
 *
 * Three rules this file exists to keep:
 *
 *  1. **No colour is hard-coded.** `index.css` defines the whole palette on `:root` and re-points
 *     it for dark, on the stated grounds that "nothing below hard-codes a colour, so the two
 *     themes cannot drift apart". Recharts cannot read CSS custom properties — it needs real
 *     colour strings — so {@link useChartTheme} resolves the tokens at runtime and repaints when
 *     the theme changes.
 *  2. **Colour is never the only channel.** The Strong/Moderate/Weak trio these charts use is the
 *     app's status palette, and measured against a colour-vision-deficiency model its warn and
 *     danger steps are very close (ΔE ~1.3 under deuteranopia). A deuteranope cannot tell those
 *     two segments apart by colour at all, so every segment ships with a legend entry, a tooltip
 *     and the same counts repeated as text beside the chart. The colour is a convenience for
 *     readers who have it, never the carrier.
 *  3. **Text wears text tokens, marks wear data colours.** Labels, axes and legends use
 *     `--text-muted`; only the bars themselves take a status or brand colour.
 */

interface ChartTheme {
  brand: string;
  brandSoft: string;
  ok: string;
  warn: string;
  danger: string;
  text: string;
  textMuted: string;
  border: string;
  surface: string;
  surfaceSunken: string;
  reducedMotion: boolean;
}

const FALLBACK: ChartTheme = {
  brand: '#0e6a5f',
  brandSoft: '#e6f2f0',
  ok: '#17643b',
  warn: '#8a5300',
  danger: '#b42318',
  text: '#101820',
  textMuted: '#5c6a78',
  border: '#dde3e9',
  surface: '#ffffff',
  surfaceSunken: '#f8fafb',
  reducedMotion: false,
};

const TOKENS: Record<keyof Omit<ChartTheme, 'reducedMotion'>, string> = {
  brand: '--brand',
  brandSoft: '--brand-soft',
  ok: '--ok',
  warn: '--warn',
  danger: '--danger',
  text: '--text',
  textMuted: '--text-muted',
  border: '--border',
  surface: '--surface',
  surfaceSunken: '--surface-sunken',
};

function readTheme(): ChartTheme {
  if (typeof window === 'undefined') return FALLBACK;
  const style = getComputedStyle(document.documentElement);
  const resolved = { ...FALLBACK };
  for (const [key, token] of Object.entries(TOKENS)) {
    const value = style.getPropertyValue(token).trim();
    // An empty string means the token did not resolve — keep the fallback rather than handing
    // recharts "", which it renders as black on both themes.
    if (value) resolved[key as keyof typeof TOKENS] = value;
  }
  resolved.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  return resolved;
}

/**
 * The palette as real colour strings, kept in step with the OS theme.
 *
 * Re-reads on a `prefers-color-scheme` change because the tokens are redefined inside that media
 * query: without this the charts keep the light palette on a surface that has gone dark, which is
 * the one regression adding a chart library can cause here.
 */
function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(readTheme);

  useEffect(() => {
    const queries = [
      window.matchMedia('(prefers-color-scheme: dark)'),
      window.matchMedia('(prefers-reduced-motion: reduce)'),
    ];
    const reread = () => setTheme(readTheme());
    queries.forEach((query) => query.addEventListener('change', reread));
    // The first paint can land before the stylesheet has applied, which resolves every token to
    // "" and pins the fallback palette for the life of the page.
    reread();
    return () => queries.forEach((query) => query.removeEventListener('change', reread));
  }, []);

  return theme;
}

/** `#rgb` or `#rrggbb` to a triple. Null for anything else, so callers can fall back. */
function parseHex(colour: string): [number, number, number] | null {
  const hex = colour.trim().replace('#', '');
  const full = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex;
  if (!/^[0-9a-f]{6}$/i.test(full)) return null;
  return [0, 2, 4].map((at) => parseInt(full.slice(at, at + 2), 16)) as [number, number, number];
}

/** `ratio` of `colour` over `onto`. Returns `colour` unchanged if either is not a hex. */
function mix(colour: string, onto: string, ratio: number): string {
  const a = parseHex(colour);
  const b = parseHex(onto);
  if (!a || !b) return colour;
  const channel = (index: number) =>
    Math.round(a[index] * ratio + b[index] * (1 - ratio))
      .toString(16)
      .padStart(2, '0');
  return `#${channel(0)}${channel(1)}${channel(2)}`;
}

/** Sized parent — `ResponsiveContainer` collapses to nothing inside a zero-height box. */
function ChartFrame({
  height,
  label,
  children,
}: {
  height: number;
  label: string;
  children: React.ReactElement;
}) {
  return (
    <div className="chart-frame" style={{ height }} role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

function TooltipBox({ theme, children }: { theme: ChartTheme; children: React.ReactNode }) {
  return (
    <div
      className="chart-tip"
      style={{ background: theme.surface, borderColor: theme.border, color: theme.text }}
    >
      {children}
    </div>
  );
}

/* ===========================================================================
   Readiness by demand band — the three levels

   A part-to-whole per band, so a stacked horizontal bar. Horizontal because the band names are
   words, and words on a vertical axis read without rotating anyone's head.
   =========================================================================== */

export interface TierDatum {
  band: DemandBand;
  label: string;
  strong: number;
  moderate: number;
  weak: number;
  total: number;
}

const SEGMENTS = [
  { key: 'strong', label: 'Strong', token: 'ok' },
  { key: 'moderate', label: 'Partly there', token: 'warn' },
  { key: 'weak', label: 'Missing', token: 'danger' },
] as const;

export function TierSplitChart({ data }: { data: TierDatum[] }) {
  const theme = useChartTheme();
  const rows = data.filter((row) => row.total > 0);

  if (rows.length === 0) return null;

  return (
    <>
      <ChartFrame
        height={Math.max(120, rows.length * 56)}
        label={
          'Skills by how much the market asks for them: '
          + rows
            .map((row) => `${row.label}, ${row.strong} strong, ${row.moderate} partly there, `
              + `${row.weak} missing, of ${row.total}`)
            .join('; ')
        }
      >
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 4, right: 8, bottom: 4, left: 8 }}
          accessibilityLayer
        >
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            width={78}
            tickLine={false}
            axisLine={false}
            tick={{ fill: theme.textMuted, fontSize: 13 }}
          />
          <Tooltip
            cursor={{ fill: theme.surfaceSunken }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as TierDatum;
              return (
                <TooltipBox theme={theme}>
                  <strong>{row.label}</strong>
                  <span>{BAND_META[row.band].blurb}</span>
                  {SEGMENTS.map((segment) => (
                    <span key={segment.key}>
                      {segment.label}: {row[segment.key]}
                    </span>
                  ))}
                </TooltipBox>
              );
            }}
          />
          {SEGMENTS.map((segment) => (
            <Bar
              key={segment.key}
              dataKey={segment.key}
              name={segment.label}
              stackId="band"
              barSize={22}
              fill={theme[segment.token]}
              // A 2px gap in the surface colour is what separates touching segments — not a
              // stroke, which would add ink that is not data.
              stroke={theme.surface}
              strokeWidth={2}
              isAnimationActive={!theme.reducedMotion}
            />
          ))}
        </BarChart>
      </ChartFrame>
      <ChartLegend
        items={SEGMENTS.map((segment) => ({ label: segment.label, color: theme[segment.token] }))}
      />
    </>
  );
}

/* ===========================================================================
   Gap to target

   Two shades of one hue: what the student has, and what is still missing between that and the
   level this career asks for. Stacked so the bar's full length is the target — the shortfall is
   the thing being read, and it is read directly rather than inferred from two separate bars.
   =========================================================================== */

export interface GapDatum {
  label: string;
  /** 0..100 attained. */
  current: number;
  /** 0..100 still needed to reach the target. */
  shortfall: number;
  /** 0..100 target, for the tooltip. */
  target: number;
  band: DemandBand;
}

export function GapChart({ data }: { data: GapDatum[] }) {
  const theme = useChartTheme();
  if (data.length === 0) return null;

  return (
    <>
      <ChartFrame
        height={Math.max(140, data.length * 42)}
        label={
          'Progress towards the level each skill is asked for: '
          + data.map((row) => `${row.label}, ${Math.round(row.current)} of ${Math.round(row.target)}`)
            .join('; ')
        }
      >
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 12, bottom: 4, left: 8 }}
          accessibilityLayer
        >
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis
            type="category"
            dataKey="label"
            width={170}
            tickLine={false}
            axisLine={false}
            tick={{ fill: theme.textMuted, fontSize: 13 }}
          />
          <Tooltip
            cursor={{ fill: theme.surfaceSunken }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as GapDatum;
              return (
                <TooltipBox theme={theme}>
                  <strong>{row.label}</strong>
                  <span>You: {Math.round(row.current)} of 100</span>
                  <span>This career asks for: {Math.round(row.target)}</span>
                  <span>{BAND_META[row.band].label} — {BAND_META[row.band].blurb}</span>
                </TooltipBox>
              );
            }}
          />
          <Bar
            dataKey="current"
            name="What you have"
            stackId="gap"
            barSize={18}
            fill={theme.brand}
            stroke={theme.surface}
            strokeWidth={2}
            isAnimationActive={!theme.reducedMotion}
          />
          <Bar
            dataKey="shortfall"
            name="Still to close"
            stackId="gap"
            barSize={18}
            fill={theme.brandSoft}
            stroke={theme.surface}
            strokeWidth={2}
            radius={[0, 4, 4, 0]}
            isAnimationActive={!theme.reducedMotion}
          />
        </BarChart>
      </ChartFrame>
      <ChartLegend
        items={[
          { label: 'What you have', color: theme.brand },
          { label: 'Still to close', color: theme.brandSoft },
        ]}
      />
    </>
  );
}

/* ===========================================================================
   Market demand — how many skills sit in each band

   Ordinal, not categorical: the bands have an order and swapping it would change the meaning, so
   the colour carries that order as one hue getting stronger rather than three unrelated hues.
   =========================================================================== */

export function MarketBandChart({
  data,
}: {
  data: { band: DemandBand; label: string; count: number }[];
}) {
  const theme = useChartTheme();
  const rows = data.filter((row) => row.count > 0);
  if (rows.length === 0) return null;

  // One hue, strongest for the band that matters most. Mixed here rather than with CSS
  // `color-mix()`: this lands in an SVG `fill` attribute, where support for CSS colour
  // functions is uneven, and a fill the browser cannot parse renders black.
  const shades: Record<DemandBand, string> = {
    critical: theme.brand,
    important: mix(theme.brand, theme.surface, 0.62),
    useful: mix(theme.brand, theme.surface, 0.3),
  };

  return (
    <ChartFrame
      height={Math.max(120, rows.length * 46)}
      label={
        'Skills this career asks for, by demand band: '
        + rows.map((row) => `${row.label}, ${row.count}`).join('; ')
      }
    >
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ top: 4, right: 36, bottom: 4, left: 8 }}
        accessibilityLayer
      >
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          width={78}
          tickLine={false}
          axisLine={false}
          tick={{ fill: theme.textMuted, fontSize: 13 }}
        />
        <Tooltip
          cursor={{ fill: theme.surfaceSunken }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as { band: DemandBand; label: string; count: number };
            return (
              <TooltipBox theme={theme}>
                <strong>{row.label}</strong>
                <span>{row.count} skills</span>
                <span>{BAND_META[row.band].blurb}</span>
              </TooltipBox>
            );
          }}
        />
        <Bar
          dataKey="count"
          name="Skills"
          barSize={22}
          radius={[0, 4, 4, 0]}
          // One series, so no legend box: the section heading already says what is plotted.
          label={{ position: 'right', fill: theme.textMuted, fontSize: 12 }}
          isAnimationActive={!theme.reducedMotion}
        >
          {rows.map((row) => (
            <Cell key={row.band} fill={shades[row.band]} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

/**
 * Legend as HTML, not recharts' own.
 *
 * The swatch beside the text is what carries identity; the text itself stays in a text token. A
 * light data colour used as label text is illegible on the surface, and the app's own rule is
 * that status is never colour alone.
 */
function ChartLegend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="chart-legend list-reset">
      {items.map((item) => (
        <li key={item.label} className="chart-legend__item">
          <span className="chart-legend__swatch" style={{ background: item.color }} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
