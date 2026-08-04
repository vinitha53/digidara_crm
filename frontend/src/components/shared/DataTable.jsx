export default function DataTable({ columns, data = [], loading, empty = "No records found.", onRow }) {
  if (loading) return <div className="skeleton table-skeleton" />;
  if (!data.length) return <div className="empty">{empty}</div>;
  return (
    <div className="table-wrap data-table-wrap">
      <table className="data-table">
        <thead><tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
        <tbody>{data.map((row) => <tr key={row.id} onClick={() => onRow?.(row)}>{columns.map((c) => <td key={c.key} data-label={c.label}>{c.render ? c.render(row) : row[c.key]}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
