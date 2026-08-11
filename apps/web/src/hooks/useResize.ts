/**
 * useResize — drag-to-resize hook for adjacent panels.
 *
 * Usage:
 *   const { size, handleProps } = useResize({ initialSize: 320, min: 180, max: 600 })
 *   <div style={{ width: size }}>...</div>
 *   <div {...handleProps} />
 */

"use client";

import { useCallback, useRef, useState } from "react";

interface UseResizeOptions {
  /** Initial size in px */
  initialSize: number;
  /** Min allowed size */
  min?: number;
  /** Max allowed size */
  max?: number;
  /** "horizontal" resizes width (default), "vertical" resizes height */
  axis?: "horizontal" | "vertical";
}

export function useResize({ initialSize, min = 100, max = 900, axis = "horizontal" }: UseResizeOptions) {
  const [size, setSize] = useState(initialSize);
  const dragging = useRef(false);
  const startPos = useRef(0);
  const startSize = useRef(initialSize);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;
      startPos.current = axis === "horizontal" ? e.clientX : e.clientY;
      startSize.current = size;

      function onMove(me: MouseEvent) {
        if (!dragging.current) return;
        const delta = axis === "horizontal"
          ? me.clientX - startPos.current
          : me.clientY - startPos.current;
        setSize(Math.min(max, Math.max(min, startSize.current + delta)));
      }
      function onUp() {
        dragging.current = false;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      }

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [size, min, max, axis],
  );

  return {
    size,
    handleProps: {
      onMouseDown,
      role: "separator" as const,
      "aria-orientation": axis === "horizontal" ? ("vertical" as const) : ("horizontal" as const),
    },
  };
}
