import { useState } from 'react';
import type { FormEvent } from 'react';
import { AppShell } from '../../components/AppShell';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { TextField } from '../../components/TextField';

import { Banner } from '../../components/Banner';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { TextArea } from '../../components/TextArea';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as adminApi from '../../api/admin';
import * as referenceApi from '../../api/reference';
import { messageFor } from '../../api/errors';
import type { CareerPathResponse, CreateCareerPathRequest, UpdateCareerPathRequest } from '../../types';

export function AdminReferencePage() {
  const { session } = useAuth();
  const token = session!.token;

  const univData = useAsync(() => referenceApi.listUniversities(token), [token]);
  const fieldData = useAsync(() => referenceApi.listStudyFields(token), [token]);
  const pathData = useAsync(() => referenceApi.listCareerPaths(token), [token]);

  const createUniv = useAction(adminApi.createUniversity);
  const createField = useAction(adminApi.createStudyField);
  const createPath = useAction(adminApi.createCareerPath);
  const updatePath = useAction(adminApi.updateCareerPath);
  const deletePath = useAction(adminApi.deleteCareerPath);

  const [univName, setUnivName] = useState('');
  const [fieldName, setFieldName] = useState('');

  const [showPathCreate, setShowPathCreate] = useState(false);
  const [pathForm, setPathForm] = useState<{ title: string; description: string; studyFieldIds: number[] }>({ title: '', description: '', studyFieldIds: [] });
  const [editingPathId, setEditingPathId] = useState<number | null>(null);
  const [deletingPath, setDeletingPath] = useState<CareerPathResponse | null>(null);

  const loading = univData.loading || fieldData.loading || pathData.loading;
  const failed = univData.failed || fieldData.failed || pathData.failed;
  const error = univData.error || fieldData.error || pathData.error;

  const handleCreateUniv = async (e: FormEvent) => {
    e.preventDefault();
    if (!univName.trim()) return;
    const res = await createUniv.run(token, { universityName: univName });
    if (res) {
      setUnivName('');
      univData.reload();
    }
  };

  const handleCreateField = async (e: FormEvent) => {
    e.preventDefault();
    if (!fieldName.trim()) return;
    const res = await createField.run(token, { fieldName: fieldName });
    if (res) {
      setFieldName('');
      fieldData.reload();
    }
  };

  const handleCreatePath = async (e: FormEvent) => {
    e.preventDefault();
    if (pathForm.studyFieldIds.length === 0) return;
    const req: CreateCareerPathRequest = {
      title: pathForm.title,
      description: pathForm.description,
      studyFieldIds: pathForm.studyFieldIds
    };
    const res = await createPath.run(token, req);
    if (res) {
      setShowPathCreate(false);
      setPathForm({ title: '', description: '', studyFieldIds: [] });
      pathData.reload();
    }
  };

  const startEditPath = (p: CareerPathResponse) => {
    setEditingPathId(p.careerPathId);
    setPathForm({
      title: p.title,
      description: p.description || '',
      studyFieldIds: p.studyFields.map(sf => sf.studyFieldId)
    });
    setShowPathCreate(false);
  };

  const handleUpdatePath = async (e: FormEvent) => {
    e.preventDefault();
    if (!editingPathId || pathForm.studyFieldIds.length === 0) return;
    const req: UpdateCareerPathRequest = {
      title: pathForm.title,
      description: pathForm.description,
      studyFieldIds: pathForm.studyFieldIds
    };
    const res = await updatePath.run(token, editingPathId, req);
    if (res) {
      setEditingPathId(null);
      setPathForm({ title: '', description: '', studyFieldIds: [] });
      pathData.reload();
    }
  };

  const handleDeletePath = async () => {
    if (!deletingPath) return;
    const res = await deletePath.run(token, deletingPath.careerPathId);
    if (res !== undefined) {
      setDeletingPath(null);
      pathData.reload();
    }
  };

  const toggleField = (id: number) => {
    setPathForm(prev => {
      const exists = prev.studyFieldIds.includes(id);
      if (exists) {
        return { ...prev, studyFieldIds: prev.studyFieldIds.filter(fid => fid !== id) };
      } else {
        return { ...prev, studyFieldIds: [...prev.studyFieldIds, id] };
      }
    });
  };

  return (
    <AppShell>
      <PageHeader 
        title="Reference data" 
        lede="Manage universities, study fields, and career paths. These are the building blocks used across the platform."
      />

      {loading && <Skeleton rows={6} />}
      {!loading && failed && <ErrorState message={messageFor(error)} onRetry={univData.reload} />}
      {!loading && !failed && (
        <div className="stack">
          {createUniv.failed && <Banner message={messageFor(createUniv.error)} />}
          {createField.failed && <Banner message={messageFor(createField.error)} />}
          {createPath.failed && <Banner message={messageFor(createPath.error)} />}
          {updatePath.failed && <Banner message={messageFor(updatePath.error)} />}
          {deletePath.failed && <Banner message={messageFor(deletePath.error)} />}

          <Card>
            <h2 className="section__title">Universities</h2>
            <form className="form__row" onSubmit={handleCreateUniv}>
              <div style={{ flex: 1 }}>
                <TextField label="New University Name" value={univName} onChange={e => setUnivName(e.target.value)} required />
              </div>
              <div style={{ marginTop: '24px' }}>
                <button type="submit" className="button button--primary" disabled={createUniv.running}>Add</button>
              </div>
            </form>
            <div className="tablewrap stack">
              <table className="table">
                <tbody>
                  {univData.data?.map(u => (
                    <tr key={u.universityId}>
                      <td>{u.universityName}</td>
                    </tr>
                  ))}
                  {univData.data?.length === 0 && <tr><td className="cell__quiet">No universities found</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <h2 className="section__title">Study Fields</h2>
            <form className="form__row" onSubmit={handleCreateField}>
              <div style={{ flex: 1 }}>
                <TextField label="New Study Field Name" value={fieldName} onChange={e => setFieldName(e.target.value)} required />
              </div>
              <div style={{ marginTop: '24px' }}>
                <button type="submit" className="button button--primary" disabled={createField.running}>Add</button>
              </div>
            </form>
            <div className="tablewrap stack">
              <table className="table">
                <tbody>
                  {fieldData.data?.map(f => (
                    <tr key={f.studyFieldId}>
                      <td>{f.fieldName}</td>
                    </tr>
                  ))}
                  {fieldData.data?.length === 0 && <tr><td className="cell__quiet">No study fields found</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <div className="posting__head">
              <h2 className="section__title">Career Paths</h2>
              <button className="button button--small" onClick={() => { setShowPathCreate(true); setEditingPathId(null); setPathForm({ title: '', description: '', studyFieldIds: [] }); }}>Add career path</button>
            </div>
            
            {(showPathCreate || editingPathId !== null) && (
              <div className="stack" style={{ marginBottom: '2rem', padding: '1rem', background: 'var(--color-bg-alt)', borderRadius: '8px' }}>
                <h3 className="section__title">{editingPathId ? 'Edit Career Path' : 'New Career Path'}</h3>
                <form className="form" onSubmit={editingPathId !== null ? handleUpdatePath : handleCreatePath}>
                  <TextField label="Title" required value={pathForm.title} onChange={e => setPathForm({...pathForm, title: e.target.value})} />
                  <TextArea label="Description" optional value={pathForm.description} onChange={e => setPathForm({...pathForm, description: e.target.value})} />
                  
                  <div className="field">
                    <label className="field__label">Linked Study Fields (Select at least one) <span className="field__required">*</span></label>
                    <div className="grid">
                      {fieldData.data?.map(f => (
                        <label key={f.studyFieldId} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <input 
                            type="checkbox" 
                            checked={pathForm.studyFieldIds.includes(f.studyFieldId)}
                            onChange={() => toggleField(f.studyFieldId)}
                          />
                          {f.fieldName}
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="actions">
                    <button type="submit" className="button button--primary" disabled={createPath.running || updatePath.running || pathForm.studyFieldIds.length === 0}>
                      {editingPathId ? 'Save Changes' : 'Create'}
                    </button>
                    <button type="button" className="button button--quiet" onClick={() => { setShowPathCreate(false); setEditingPathId(null); }}>Cancel</button>
                  </div>
                </form>
              </div>
            )}

            <div className="stack">
              {pathData.data?.length === 0 ? (
                <EmptyState title="No career paths found" body="Create a career path to get started." />
              ) : (
                pathData.data?.map(p => (
                  <div key={p.careerPathId} className="posting">
                    <div className="posting__head">
                      <h3 className="posting__title">{p.title}</h3>
                      <div className="posting__actions">
                        <button className="button button--small" onClick={() => startEditPath(p)}>Edit</button>
                        <button className="button button--small button--danger" onClick={() => setDeletingPath(p)}>Delete</button>
                      </div>
                    </div>
                    {p.description && <p className="posting__description">{p.description}</p>}
                    <div className="posting__meta">
                      <strong>Study Fields:</strong> {p.studyFields.map(sf => sf.fieldName).join(', ')}
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
          
          {deletingPath && (
            <ConfirmDialog
              title="Delete career path"
              body={`Are you sure you want to delete "${deletingPath.title}"?`}
              confirmLabel="Delete"
              destructive
              busy={deletePath.running}
              onConfirm={handleDeletePath}
              onCancel={() => setDeletingPath(null)}
            />
          )}
        </div>
      )}
    </AppShell>
  );
}
