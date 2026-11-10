import { ArrowLeft, SearchX } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, Card } from "../components/ui";

export function NotFoundPage() {
  return (
    <div className="page-stack">
      <Card>
        <div className="empty-state">
          <div className="empty-icon"><SearchX size={21} /></div>
          <h3>Page not found</h3>
          <p>We couldn’t find the page you’re looking for.</p>
          <Link className="button button-secondary" to="/"><ArrowLeft size={15} /> Back to homepage</Link>
        </div>
      </Card>
    </div>
  );
}
