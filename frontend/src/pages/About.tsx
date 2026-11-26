import { Link } from '../Nav'

export default function About() {
  return <article className="page panel">
    <h2>About</h2>
    <p>A free, ad-free Ludo for two to four players. Pass one device around, or create a private online room and share the invite link with friends.</p>
    <h3>Features</h3>
    <ul>
      <li>Pass-and-play on one device, or private online rooms for 2–4 players.</li>
      <li>Turn timers, live player status, and computer substitutes for players who drop out.</li>
      <li>In-game chat, quick messages and playful emotes, with muting for anyone you'd rather not hear.</li>
      <li>Optional account to keep your name and avatar, see your wins, and resume online games on any device.</li>
      <li>Works on phones, tablets and desktops; respects reduced-motion settings.</li>
    </ul>
    <h3>Privacy</h3>
    <ul>
      <li>No ads, no tracking, no cookies. Your browser keeps your current seat and sign-in in its local storage.</li>
      <li>Rooms store the board, player names and avatars, and the room’s chat. Finished rooms are deleted after two days and idle rooms after thirty.</li>
      <li>An account stores your username, email address, a salted password hash, your profile and your game results. Your email is used only for sign-up and password-reset codes. You can delete your account at any time from <Link to="/account">your account page</Link>.</li>
      <li>Your network address is used only briefly, in memory, to limit abuse.</li>
    </ul>
    <h3>Fair play</h3>
    <p>The server rolls every die and checks every move, so the game can't be tampered with from a browser.</p>
  </article>
}
