export default function Rules() {
  return <article className="page panel">
    <h2>How to play</h2>
    <p>Move all four of your pawns from your yard, around the board, up your colored home lane and into the center. The first player to bring every pawn home wins.</p>
    <h3>Your turn</h3>
    <ul>
      <li>Tap the die beside your portrait to roll it.</li>
      <li>Roll a <strong>6</strong> to bring a pawn out onto your start square.</li>
      <li>Tap a glowing pawn to move it forward by the number rolled. Pawns travel clockwise.</li>
      <li>If no pawn can move, the turn passes (a 6 still lets you roll again).</li>
    </ul>
    <h3>Extra rolls</h3>
    <ul>
      <li>Roll again after a 6, after capturing, or after bringing a pawn home.</li>
      <li>A third 6 in a row forfeits the roll and ends your turn.</li>
    </ul>
    <h3>Captures and safe squares</h3>
    <ul>
      <li>Land on an opponent's pawn on an ordinary square to send it back to its yard. Every opposing pawn on that square goes back.</li>
      <li>Start squares and starred squares are safe: nobody can be captured there.</li>
      <li>Pawns can pass each other; stacks never block the way.</li>
      <li>A pawn needs the exact number to reach the center.</li>
    </ul>
    <h3>Online games</h3>
    <ul>
      <li>You have <strong>5 seconds to roll</strong> (a ring drains around the die) and <strong>15 seconds to move</strong> (a ring drains around your portrait; it turns red and blinks in the last 5). When time runs out the game rolls, or moves a random pawn, for you.</li>
      <li>If your connection drops, the game keeps playing your turns. Reopen the game in the same browser and choose <em>Resume game</em>, or sign in on any device and resume from <em>Your online games</em>.</li>
      <li>After 5 minutes away, a computer takes over your seat if the room allows substitutes; otherwise you are removed. You can still return while a computer plays for you.</li>
      <li><em>Leave game</em> gives up your seat for good. When only one player remains, they win.</li>
      <li>Turn on <em>Move automatically</em> to skip the tap when only one pawn can move.</li>
    </ul>
  </article>
}
