import type { ReactNode } from "react";

import { cx } from "./cx";

export type Column<Row> = {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
  /** "end" para números, que também passam a usar a fonte de dados. */
  align?: "start" | "end";
  /** Horários, contagens e IDs: fonte mono com algarismos tabulares. */
  data?: boolean;
};

export type DataTableProps<Row> = {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  /** Descrição da tabela para leitores de tela. */
  caption: string;
  /** Mostrado no lugar da tabela quando não há linhas. */
  empty: ReactNode;
};

export function DataTable<Row>({ columns, rows, rowKey, caption, empty }: DataTableProps<Row>) {
  if (rows.length === 0) {
    return <p className="av-table__empty text-body">{empty}</p>;
  }
  return (
    <div className="av-table">
      <table>
        <caption className="av-visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={cx("text-label", column.align === "end" && "av-table__end")}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cx(
                    column.align === "end" && "av-table__end",
                    (column.data || column.align === "end") && "text-data",
                  )}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
