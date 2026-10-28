package tn.tuntransport.sharing

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** État du partage en cours, observé par l'interface et mis à jour par [ShareService]. */
object ShareSession {
    sealed interface State {
        data object Idle : State

        data class Active(
            val lineId: String,
            val directionIndex: Int,
            val lineLabel: String,
            val headsign: String,
            val status: Status,
        ) : State
    }

    sealed interface Status {
        /** Pas encore assez de points pour valider ligne et sens : rien n'est diffusé. */
        data object Checking : Status
        data class OnRoute(val alongM: Double, val speedMps: Double) : Status
        data class Rejected(val reason: String) : Status
    }

    private val mutableState = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = mutableState.asStateFlow()

    internal fun update(state: State) {
        mutableState.value = state
    }
}
