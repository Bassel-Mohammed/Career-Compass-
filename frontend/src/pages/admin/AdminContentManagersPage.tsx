import { useState } from 'react';
import type { FormEvent } from 'react';
import { AppShell } from '../../components/AppShell';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { TextField } from '../../components/TextField';
import { Select } from '../../components/Select';
import { Banner } from '../../components/Banner';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as adminApi from '../../api/admin';
import * as referenceApi from '../../api/reference';
import { messageFor } from '../../api/errors';
import { formatDate } from '../../api/format';
import type { ContentManagerResponse, CreateContentManagerRequest, UpdateContentManagerRequest } from '../../types';

export function AdminContentManagersPage() {
  const { session } = useAuth();
  const token = session!.token;

  const data = useAsync(() => adminApi.listContentManagers(token), [token]);
  const univData = useAsync(() => referenceApi.listUniversities(token), [token]);
  const fieldData = useAsync(() => referenceApi.listStudyFields(token), [token]);

  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const create = useAction(adminApi.createContentManager);
  const update = useAction(adminApi.updateContentManager);
  const toggleActive = useAction(adminApi.setContentManagerActive);

  const loading = data.loading || univData.loading || fieldData.loading;
  const failed = data.failed || univData.failed || fieldData.failed;
  const error = data.error || univData.error || fieldData.error;

  const univOptions = univData.data?.map(u => ({ value: u.universityId.toString(), label: u.universityName })) || [];
  const fieldOptions = fieldData.data?.map(f => ({ value: f.studyFieldId.toString(), label: f.fieldName })) || [];
  fieldOptions.unshift({ value: '', label: 'None' });

  // Create Form State
  const [createForm, setCreateForm] = useState({
    firstName: '', lastName: '', email: '', initialPassword: '', universityId: '', studyFieldId: ''
  });

  // Edit Form State
  const [editForm, setEditForm] = useState({
    firstName: '', lastName: '', universityId: '', studyFieldId: ''
  });

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    const req: CreateContentManagerRequest = {
      firstName: createForm.firstName,
      lastName: createForm.lastName,
      email: createForm.email,
      initialPassword: createForm.initialPassword,
      universityId: parseInt(createForm.universityId, 10),
      studyFieldId: createForm.studyFieldId ? parseInt(createForm.studyFieldId, 10) : undefined
    };
    const res = await create.run(token, req);
    if (res) {
      setShowCreate(false);
      setCreateForm({ firstName: '', lastName: '', email: '', initialPassword: '', universityId: '', studyFieldId: '' });
      data.reload();
    }
  };

  const startEdit = (cm: ContentManagerResponse) => {
    setEditingId(cm.contentManagerId);
    setEditForm({
      firstName: cm.firstName,
      lastName: cm.lastName,
      universityId: cm.universityId ? cm.universityId.toString() : '',
      studyFieldId: cm.studyFieldId ? cm.studyFieldId.toString() : ''
    });
  };

  const handleUpdate = async (e: FormEvent) => {
    e.preventDefault();
    if (!editingId) return;
    const req: UpdateContentManagerRequest = {
      firstName: editForm.firstName,
      lastName: editForm.lastName,
      universityId: parseInt(editForm.universityId, 10),
      studyFieldId: editForm.studyFieldId ? parseInt(editForm.studyFieldId, 10) : undefined
    };
    const res = await update.run(token, editingId, req);
    if (res) {
      setEditingId(null);
      data.reload();
    }
  };

  const handleToggle = async (id: number, active: boolean) => {
    await toggleActive.run(token, id, active);
    data.reload();
  };

  return (
    <AppShell>
      <PageHeader 
        title="Content managers" 
        lede="Create and manage content manager accounts. Each content manager is assigned to a university and can upload learning outcomes."
        action={<button className="button button--primary" onClick={() => setShowCreate(true)}>Add content manager</button>}
      />

      {loading && <Skeleton rows={4} />}
      {!loading && failed && <ErrorState message={messageFor(error)} onRetry={data.reload} />}
      {!loading && !failed && (
        <div className="stack">
          {create.failed && <Banner message={messageFor(create.error)} />}
          {update.failed && <Banner message={messageFor(update.error)} />}
          {toggleActive.failed && <Banner message={messageFor(toggleActive.error)} />}

          {showCreate && (
            <Card>
              <h2 className="section__title">Add content manager</h2>
              <form className="form" onSubmit={handleCreate}>
                <div className="form__row">
                  <TextField label="First Name" required value={createForm.firstName} onChange={e => setCreateForm({...createForm, firstName: e.target.value})} />
                  <TextField label="Last Name" required value={createForm.lastName} onChange={e => setCreateForm({...createForm, lastName: e.target.value})} />
                </div>
                <div className="form__row">
                  <TextField label="Email" type="email" required value={createForm.email} onChange={e => setCreateForm({...createForm, email: e.target.value})} />
                  <TextField label="Initial Password" type="password" required value={createForm.initialPassword} onChange={e => setCreateForm({...createForm, initialPassword: e.target.value})} />
                </div>
                <div className="form__row">
                  <Select label="University" options={univOptions} required value={createForm.universityId} onChange={e => setCreateForm({...createForm, universityId: e.target.value})} />
                  <Select label="Study Field" options={fieldOptions} optional value={createForm.studyFieldId} onChange={e => setCreateForm({...createForm, studyFieldId: e.target.value})} />
                </div>
                <div className="actions">
                  <button type="submit" className="button button--primary" disabled={create.running}>Save</button>
                  <button type="button" className="button button--quiet" onClick={() => setShowCreate(false)}>Cancel</button>
                </div>
              </form>
            </Card>
          )}

          {editingId !== null && (
            <Card>
              <h2 className="section__title">Edit content manager</h2>
              <form className="form" onSubmit={handleUpdate}>
                <div className="form__row">
                  <TextField label="First Name" required value={editForm.firstName} onChange={e => setEditForm({...editForm, firstName: e.target.value})} />
                  <TextField label="Last Name" required value={editForm.lastName} onChange={e => setEditForm({...editForm, lastName: e.target.value})} />
                </div>
                <div className="form__row">
                  <Select label="University" options={univOptions} required value={editForm.universityId} onChange={e => setEditForm({...editForm, universityId: e.target.value})} />
                  <Select label="Study Field" options={fieldOptions} optional value={editForm.studyFieldId} onChange={e => setEditForm({...editForm, studyFieldId: e.target.value})} />
                </div>
                <div className="actions">
                  <button type="submit" className="button button--primary" disabled={update.running}>Save Changes</button>
                  <button type="button" className="button button--quiet" onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              </form>
            </Card>
          )}

          {data.data?.length === 0 ? (
            <EmptyState title="No content managers found" body="Create a content manager to get started." />
          ) : (
            <div className="tablewrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>University</th>
                    <th>Study Field</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data?.map(cm => (
                    <tr key={cm.contentManagerId}>
                      <td data-label="Name">{cm.firstName} {cm.lastName}</td>
                      <td data-label="Email">{cm.email}</td>
                      <td data-label="University">{cm.universityName || '—'}</td>
                      <td data-label="Study Field">{cm.studyFieldName || '—'}</td>
                      <td data-label="Status">
                        <span className={`badge ${cm.isActive ? 'badge--strong' : 'badge--weak'}`}>
                          {cm.isActive ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td data-label="Created">{formatDate(cm.createdAt)}</td>
                      <td data-label="Actions" className="cell--narrow">
                        <div className="actions">
                          <button className="button button--small" onClick={() => startEdit(cm)}>Edit</button>
                          <button className="button button--small button--quiet" onClick={() => handleToggle(cm.contentManagerId, !cm.isActive)} disabled={toggleActive.running}>
                            {cm.isActive ? 'Deactivate' : 'Activate'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
