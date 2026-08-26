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
import type { CreateExpertRequest } from '../../types';

export function AdminMentorsPage() {
  const { session } = useAuth();
  const token = session!.token;

  const data = useAsync(() => adminApi.listExperts(token), [token]);
  const fieldData = useAsync(() => referenceApi.listStudyFields(token), [token]);

  const [showCreate, setShowCreate] = useState(false);
  const create = useAction(adminApi.createExpert);

  const loading = data.loading || fieldData.loading;
  const failed = data.failed || fieldData.failed;
  const error = data.error || fieldData.error;

  const fieldOptions = fieldData.data?.map(f => ({ value: f.studyFieldId.toString(), label: f.fieldName })) || [];
  fieldOptions.unshift({ value: '', label: 'None' });

  const [createForm, setCreateForm] = useState({
    firstName: '', lastName: '', email: '', initialPassword: '', studyFieldId: '', fieldStartingYear: '2020'
  });

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    const req: CreateExpertRequest = {
      firstName: createForm.firstName,
      lastName: createForm.lastName,
      email: createForm.email,
      initialPassword: createForm.initialPassword,
      studyFieldId: createForm.studyFieldId ? parseInt(createForm.studyFieldId, 10) : undefined,
      fieldStartingYear: parseInt(createForm.fieldStartingYear, 10)
    };
    const res = await create.run(token, req);
    if (res) {
      setShowCreate(false);
      setCreateForm({ firstName: '', lastName: '', email: '', initialPassword: '', studyFieldId: '', fieldStartingYear: '2020' });
      data.reload();
    }
  };

  return (
    <AppShell>
      <PageHeader 
        title="Mentors" 
        lede="Create mentor accounts. Mentors provide expert consultations to students in their study field."
        action={<button className="button button--primary" onClick={() => setShowCreate(true)}>Add mentor</button>}
      />

      {loading && <Skeleton rows={4} />}
      {!loading && failed && <ErrorState message={messageFor(error)} onRetry={data.reload} />}
      {!loading && !failed && (
        <div className="stack">
          {create.failed && <Banner message={messageFor(create.error)} />}

          {showCreate && (
            <Card>
              <h2 className="section__title">Add mentor</h2>
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
                  <Select label="Study Field" options={fieldOptions} optional value={createForm.studyFieldId} onChange={e => setCreateForm({...createForm, studyFieldId: e.target.value})} />
                  <TextField label="Field Starting Year" type="number" required min={1950} max={2026} value={createForm.fieldStartingYear} onChange={e => setCreateForm({...createForm, fieldStartingYear: e.target.value})} />
                </div>
                <div className="actions">
                  <button type="submit" className="button button--primary" disabled={create.running}>Save</button>
                  <button type="button" className="button button--quiet" onClick={() => setShowCreate(false)}>Cancel</button>
                </div>
              </form>
            </Card>
          )}

          {data.data?.length === 0 ? (
            <EmptyState title="No mentors found" body="Create a mentor to get started." />
          ) : (
            <div className="tablewrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Study Field</th>
                    <th>Field since</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data?.map(m => (
                    <tr key={m.expertId}>
                      <td data-label="Name">{m.firstName} {m.lastName}</td>
                      <td data-label="Email">{m.email}</td>
                      <td data-label="Study Field">{m.studyFieldName || '—'}</td>
                      <td data-label="Field since">{m.fieldStartingYear}</td>
                      <td data-label="Status">
                        <span className={`badge ${m.statusName === 'Active' ? 'badge--strong' : 'badge--weak'}`}>
                          {m.statusName}
                        </span>
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
