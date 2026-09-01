import { useState } from 'react';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { Select } from '../../components/Select';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as expertApi from '../../api/expert';
import { messageFor } from '../../api/errors';
import { DAY_NAMES, toLocalTime, fromLocalTime } from '../../api/format';
import type { AvailabilitySlotRequest } from '../../types';

export function ExpertAvailabilityPage() {
  const { session } = useAuth();
  const token = session!.token;
  
  const profile = useAsync(() => expertApi.getProfile(token), [token]);
  const updateStatus = useAction(expertApi.setActive);
  const updateSlots = useAction(expertApi.updateAvailability);

  const [slots, setSlots] = useState<AvailabilitySlotRequest[]>([]);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Status toggle
  const handleToggleStatus = async () => {
    if (!profile.data) return;
    const isActive = profile.data.statusName === 'Active';
    const res = await updateStatus.run(token, !isActive);
    if (res) {
      profile.setData(res);
    }
  };

  const addSlot = () => {
    setSlots([...slots, { dayOfWeek: 1, startTime: '09:00', endTime: '17:00' }]);
    setSaveSuccess(false);
  };

  const removeSlot = (index: number) => {
    setSlots(slots.filter((_, i) => i !== index));
    setSaveSuccess(false);
  };

  const updateSlot = (index: number, field: keyof AvailabilitySlotRequest, value: any) => {
    const newSlots = [...slots];
    newSlots[index] = { ...newSlots[index], [field]: value };
    setSlots(newSlots);
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    const formattedSlots = slots.map(s => ({
      dayOfWeek: Number(s.dayOfWeek),
      startTime: s.startTime.length === 5 ? toLocalTime(s.startTime) : s.startTime,
      endTime: s.endTime.length === 5 ? toLocalTime(s.endTime) : s.endTime
    }));
    
    const res = await updateSlots.run(token, { slots: formattedSlots });
    if (res) {
      setSaveSuccess(true);
      // Map returned slots to local format for editing
      setSlots(res.map(s => ({
        ...s,
        startTime: fromLocalTime(s.startTime),
        endTime: fromLocalTime(s.endTime)
      })));
    }
  };

  const isLoading = profile.loading;
  const isFailed = profile.failed;

  return (
    <AppShell>
      <PageHeader title="Manage Availability" lede="Set your weekly recurring available time slots for student sessions." />

      {(updateStatus.failed || updateSlots.failed) && (
        <Banner message={messageFor(updateStatus.error || updateSlots.error)} />
      )}

      {isLoading && <Skeleton rows={6} />}
      {!isLoading && isFailed && (
        <ErrorState message={messageFor(profile.error)} onRetry={profile.reload} />
      )}
      
      {!isLoading && !isFailed && profile.data && (
        <div className="stack stack--large">
          <Card as="section">
            <h2 className="section__title">Expert Status</h2>
            <p>Your profile is currently <strong>{profile.data.statusName}</strong>.</p>
            <p className="cell__quiet">Only Active mentors appear to students browsing their field.</p>
            <div className="actions" style={{ marginTop: '1rem' }}>
              <button 
                className={`button ${profile.data.statusName === 'Active' ? 'button--danger' : 'button--primary'}`}
                onClick={handleToggleStatus}
                disabled={updateStatus.running}
              >
                {profile.data.statusName === 'Active' ? 'Deactivate Profile' : 'Activate Profile'}
              </button>
            </div>
          </Card>

          <Card as="section">
            <h2 className="section__title">Weekly Time Slots</h2>
            
            {saveSuccess && (
              <div className="notice notice--ok" style={{ marginBottom: '1rem' }}>
                Availability updated successfully.
              </div>
            )}

            {slots.length === 0 ? (
              <EmptyState 
                title="No availability set" 
                body="Add time slots below to let students know when they can book a consultation with you." 
              />
            ) : (
              <ul className="list-reset stack stack--small">
                {slots.map((slot, i) => (
                  <li key={i} className="form__row" style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end' }}>
                    <div style={{ flex: 1 }}>
                      <Select
                        label="Day of week"
                        value={slot.dayOfWeek.toString()}
                        onChange={e => updateSlot(i, 'dayOfWeek', Number(e.target.value))}
                        options={DAY_NAMES.map((name, idx) => ({ value: String(idx + 1), label: name }))}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label className="field">
                        <span className="field__label">Start Time</span>
                        <input 
                          type="time" 
                          className="field__input"
                          value={slot.startTime} 
                          onChange={e => updateSlot(i, 'startTime', e.target.value)} 
                        />
                      </label>
                    </div>
                    <div style={{ flex: 1 }}>
                      <label className="field">
                        <span className="field__label">End Time</span>
                        <input 
                          type="time" 
                          className="field__input"
                          value={slot.endTime} 
                          onChange={e => updateSlot(i, 'endTime', e.target.value)} 
                        />
                      </label>
                    </div>
                    <button 
                      className="button button--quiet button--danger"
                      onClick={() => removeSlot(i)}
                      title="Remove slot"
                      style={{ marginBottom: '2px' }}
                    >
                      &times;
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="actions" style={{ marginTop: '1.5rem' }}>
              <button className="button button--secondary" onClick={addSlot}>Add time slot</button>
              <button 
                className="button button--primary" 
                onClick={handleSave}
                disabled={updateSlots.running}
              >
                Save Availability
              </button>
            </div>
          </Card>
        </div>
      )}
    </AppShell>
  );
}
