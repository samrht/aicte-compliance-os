import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import CaseFile from "../components/CaseFile";
import { ErrorNote, usePoll } from "../components/ui";

export default function InstCase() {
  const id = Number(useParams().id);
  const { data, error } = usePoll(() => api.application(id), 900, [id]);
  if (!data) return <ErrorNote error={error} />;
  return (
    <>
      <Link to="/inst" className="mb-4 inline-block text-[14px] text-seal">Back to your applications</Link>
      <CaseFile app={data} />
    </>
  );
}
