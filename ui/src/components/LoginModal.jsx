import { useState } from 'react';
import './LoginModal.css';

export function LoginModal({ isOpen, onClose, onLogin }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await onLogin(password);
      if (result.success) {
        onClose();
        setPassword('');
      } else {
        setError(result.error || 'Incorrect password');
      }
    } catch (err) {
      setError('Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setPassword('');
    setError('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={handleCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Admin Authentication</h2>
          <button className="modal-close" onClick={handleCancel}>&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="modal-body">
          <div className="form-group">
            <label htmlFor="admin-password">Enter admin password:</label>
            <input
              id="admin-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              required
              disabled={loading}
              className="form-control"
              placeholder="Password"
            />
          </div>

          {error && (
            <div className="alert alert-error">
              {error}
            </div>
          )}

          <div className="modal-footer">
            <button
              type="button"
              onClick={handleCancel}
              className="btn btn-secondary"
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
            >
              {loading ? 'Authenticating...' : 'Login'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
