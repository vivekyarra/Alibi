import { reasonText } from "../text";

export function ReasonList({ reasons }: { reasons: string[] }) {
  return (
    <div className="reasons">
      <h3 className="small-heading">Reasons</h3>
      <ul>
        {reasons.map((code) => (
          <li key={code}>
            <code>{code}</code>
            {reasonText(code) && <span>: {reasonText(code)}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
