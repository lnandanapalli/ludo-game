import type { Profile } from './api'
import { portraits } from './profiles'

export default function ProfilePicker({ seat, profile, change }: {
  seat: string; profile: Profile; change: (profile: Profile) => void
}) {
  return <fieldset className="profile-picker" data-seat={seat}><legend>{seat} player</legend>
    <input aria-label={seat + ' player name'} maxLength={24} placeholder="Player name" value={profile.name}
      onChange={e => change({...profile, name: e.target.value})}/>
    <div className="portraits">{Object.entries(portraits).map(([id, face]) =>
      <button key={id} type="button" aria-label={seat + ' ' + id} aria-pressed={profile.avatar === id}
        onClick={() => change({...profile, avatar: id})}>{face}</button>)}</div>
  </fieldset>
}
