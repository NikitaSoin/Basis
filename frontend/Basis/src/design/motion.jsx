// =============================================================
// BASIS MOTION — Phase 4b: dosed "appear" of cards / sections.
// Pure JS (no TS). No new packages — CSS transition only.
//
// THE RULE (same породы как count-up в портфеле):
// The appear plays EXACTLY ONCE, on the FIRST mount of a page/tab.
// It MUST NOT replay on: tab switch back-and-forth, re-render,
// background refresh (5s price poll), or clicks.
//
// MECHANISM:
//  • `gate` — a caller-owned `Set` living in a `useRef` at the PAGE
//    level (e.g. `const appearGate = useRef(new Set())` in CompanyCard
//    or each page-view). It survives tab switches and re-renders.
//  • On MOUNT (useEffect [], once): if `gate.has(groupId)` (or reduced
//    motion) → children render straight at the FINAL state (no anim,
//    no leftover inline transform). Otherwise `gate.add(groupId)` and
//    flip `shown` false→true on the next frame, which triggers the CSS
//    transition with per-child `transitionDelay = index * stagger`.
//  • On RE-MOUNT (returning to a tab): `gate.has(groupId) === true`
//    → children appear instantly at final, no replay.
//  • On RE-RENDER (no remount): `shown` state is preserved → no replay.
//
// IMPORTANT: after the appear finishes we STRIP the inline transform so
// the card returns to class-driven behaviour (e.g. hover -translate-y);
// an inline `transform` would otherwise permanently beat hover classes.
//
// AppearGroup / AppearItem are declared at MODULE level (stable identity)
// so they are never remounted by a parent's re-render.
// =============================================================
import React, { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "./primitives";

const TRANSITION =
  "opacity var(--motion-appear) var(--ease-out), transform var(--motion-appear) var(--ease-out)";

// Stagger (ms) between adjacent children. Dosed — light "coming alive".
const DEFAULT_STAGGER = 30;

// Wraps ONE appearing child. Owns the start→final flip and clears its
// inline animation styles once the transition ends, so nothing (e.g. a
// hover transform class) stays overridden by a leftover inline transform.
function AppearItem({ child, index, stagger, maxStagger }) {
  const [done, setDone] = useState(false); // animation complete → drop inline anim styles
  const [shown, setShown] = useState(false); // start (false) → final (true)

  useEffect(() => {
    const raf = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  const isEl = React.isValidElement(child);
  const baseStyle = isEl && child.props.style ? child.props.style : {};

  // Once finished, render child with only its own style (no anim leftovers).
  if (done) {
    if (!isEl) return <div>{child}</div>;
    return child;
  }

  const delayN = Math.min(index, maxStagger);
  const animStyle = {
    ...baseStyle,
    opacity: shown ? 1 : 0,
    transform: shown ? "translateY(0)" : "translateY(8px)",
    transition: TRANSITION,
    transitionDelay: `${delayN * stagger}ms`,
  };
  const onTransitionEnd = (e) => {
    // only react to our own opacity transition (ignore bubbling from kids)
    if (e.target === e.currentTarget && e.propertyName === "opacity") setDone(true);
  };

  if (!isEl) {
    return (
      <div style={animStyle} onTransitionEnd={onTransitionEnd}>
        {child}
      </div>
    );
  }
  return React.cloneElement(child, {
    style: animStyle,
    onTransitionEnd: (e) => {
      onTransitionEnd(e);
      if (typeof child.props.onTransitionEnd === "function") child.props.onTransitionEnd(e);
    },
  });
}

/**
 * AppearGroup — wraps a container and animates the FIRST appearance of
 * its direct children with a staggered fade + 4px rise.
 *
 * Props:
 *  • gate (Set, required): page-level Set of already-shown group ids.
 *  • groupId (string, required): unique id for this group within the page.
 *  • as (string): container tag, default "div".
 *  • className, style: passed to the container.
 *  • stagger (ms): per-child delay, default 30.
 *  • maxStagger (number): cap stagger to first N children (long lists →
 *    no long wave through hundreds of rows). Beyond N, delay = N*stagger.
 *  • children: staggered as direct items.
 */
export function AppearGroup({
  gate,
  groupId,
  as: Tag = "div",
  className,
  style,
  stagger = DEFAULT_STAGGER,
  maxStagger = Infinity,
  children,
  ...rest
}) {
  const reduced = usePrefersReducedMotion();
  // `already` decided ONCE on mount: reduced-motion or this group was shown
  // before on this page (tab revisit / remount) → final, no animation.
  const alreadyRef = useRef(reduced || (gate ? gate.has(groupId) : false));

  useEffect(() => {
    if (!alreadyRef.current && gate) gate.add(groupId);
    // run once on mount; no deps that would replay it.
  }, []);

  // No animation (reduced / revisit): render children untouched, no inline anim.
  if (alreadyRef.current || reduced) {
    return (
      <Tag className={className} style={style} {...rest}>
        {children}
      </Tag>
    );
  }

  const items = React.Children.toArray(children);
  return (
    <Tag className={className} style={style} {...rest}>
      {items.map((child, i) => (
        <AppearItem
          key={React.isValidElement(child) && child.key != null ? child.key : i}
          child={child}
          index={i}
          stagger={stagger}
          maxStagger={maxStagger}
        />
      ))}
    </Tag>
  );
}

/**
 * Appear — single-element variant (no stagger). Same gate/groupId rules.
 */
export function Appear({ gate, groupId, children, ...rest }) {
  return (
    <AppearGroup gate={gate} groupId={groupId} stagger={0} {...rest}>
      {children}
    </AppearGroup>
  );
}
