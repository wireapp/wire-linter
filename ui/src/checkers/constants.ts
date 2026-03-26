/**
 * Shared constants for Wire service checkers.
 *
 * Centralises lists that multiple checkers reference so a service
 * addition or removal only needs a single edit.
 */

// The 8 core Wire services — same list as WIRE_CORE_SERVICES in Python
export const WIRE_CORE_SERVICES: string[] = [
    'brig', 'galley', 'gundeck', 'cannon',
    'cargohold', 'spar', 'nginz', 'background-worker',
]
