import type { CSSProperties } from "react";

export const tableStyle: CSSProperties = { borderCollapse: "collapse", width: "100%", fontSize: 14 };
export const headerRowStyle: CSSProperties = { background: "#f1f5f9", textAlign: "left" };
export const cellStyle: CSSProperties = { padding: "8px 12px", borderBottom: "1px solid #e2e8f0", textAlign: "left" };
export const numericCellStyle: CSSProperties = {
  ...cellStyle,
  textAlign: "right",
  fontVariantNumeric: "tabular-nums",
};
export const subtleTextStyle: CSSProperties = { color: "#64748b", fontSize: 13 };
