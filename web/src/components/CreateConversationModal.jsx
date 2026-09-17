import { useState } from "react";
import "./CreateConversationModal.css";

function CreateConversationModal({ onCreate, onClose }) {
  const [name, setName] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const handleSubmit = (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);

    onCreate(name.trim())
      .then(onClose)
      .catch((err) => setError(err.message))
      .finally(() => setSaving(false));
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="modal" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmit}>
        <h2>New conversation</h2>
        <input
          className="modal__input"
          type="text"
          placeholder="Conversation name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoFocus
        />
        {error && <p className="modal__error">{error}</p>}
        <div className="modal__actions">
          <button type="button" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="modal__save" disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default CreateConversationModal;
