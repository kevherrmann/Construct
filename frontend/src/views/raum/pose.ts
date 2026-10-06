import type { Lage, Phase } from './lage'

/** 'arbeiten' ist keine Pose am Podest: dafür geht die Figur an die Werkbank
 *  und tippt dort an der Tastatur (statt in die Luft). 'sitzen' = gelangweilt im
 *  Bürostuhl eines Mitarbeiters, der gerade an der Werkbank steht. */
export type Pose = 'idle' | 'denken' | 'lesen' | 'arbeiten' | 'erklaeren' | 'sitzen'

export const POSE_VON: Record<Phase, Pose> = {
  ruht: 'idle',
  denkt: 'denken',
  wartet: 'denken',
  liest: 'lesen',
  sucht: 'lesen',
  recherchiert: 'lesen',
  schreibt: 'arbeiten',
  terminal: 'arbeiten',
  werkzeug: 'arbeiten',
  delegiert: 'arbeiten',
  antwortet: 'erklaeren',
}

/**
 * Was die Figur am Podest tun soll. Fragst du nichts, arbeitet sie aber als
 * Chefin für die Firma, folgt sie ihrem Zug, genau wie die Blase: denkt sie, steht
 * dort „denkt nach …“, also denkt auch die Figur. Vorher war das fest „erklaeren“,
 * und ab dem zweiten Zug der Chefin redete die Figur, während die Blase nachdachte.
 * An die Werkbank geht sie für die Firma nicht (Werkzeuge der Chefin sind Bus-
 * Aufrufe, also Reden), und ein fertiger Zug, der noch als aktiv gilt, ist Reden.
 * `chef` = Lage ihres Zugs, null = sie hat gerade keinen.
 * Hat sie gar nichts zu tun, während ein Mitarbeiter arbeitet (`langeweile`), setzt
 * sie sich auf dessen Stuhl.
 */
export function zielPose(eigene: Lage, chef: Lage | null, langeweile = false): Pose {
  if (!eigene.live && eigene.phase === 'ruht' && !chef) return langeweile ? 'sitzen' : 'idle'
  if (eigene.live || eigene.phase !== 'ruht' || !chef) return POSE_VON[eigene.phase]
  const p = POSE_VON[chef.phase]
  return p === 'arbeiten' || p === 'idle' ? 'erklaeren' : p
}
