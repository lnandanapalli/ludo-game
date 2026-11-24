const faces = [[4], [0, 8], [0, 4, 8], [0, 2, 6, 8], [0, 2, 4, 6, 8], [0, 2, 3, 5, 6, 8]]

export default function Die({ value }: { value: number }) {
  return <span className="die-face" aria-hidden="true">
    {(faces[(value || 1) - 1]).map(index =>
      <i key={index} style={{ gridRow: Math.floor(index / 3) + 1, gridColumn: index % 3 + 1 }} />
    )}
  </span>
}
