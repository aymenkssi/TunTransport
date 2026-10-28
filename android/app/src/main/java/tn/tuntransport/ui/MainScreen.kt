package tn.tuntransport.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import tn.tuntransport.R
import tn.tuntransport.data.Mode
import tn.tuntransport.data.Network
import tn.tuntransport.data.NetworkRepository
import tn.tuntransport.data.TransitLine
import tn.tuntransport.sharing.ShareService
import tn.tuntransport.sharing.ShareSession
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt

private sealed interface Loading {
    data object InProgress : Loading
    data object Missing : Loading
    data class Ready(val network: Network) : Loading
}

@Composable
fun MainScreen() {
    val context = LocalContext.current
    val loading by produceState<Loading>(Loading.InProgress) {
        value = withContext(Dispatchers.IO) { NetworkRepository.load(context) }
            ?.let { Loading.Ready(it) } ?: Loading.Missing
    }
    val sharing by ShareSession.state.collectAsStateWithLifecycle()
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var directionIndex by rememberSaveable { mutableIntStateOf(0) }

    val network = (loading as? Loading.Ready)?.network
    val active = sharing as? ShareSession.State.Active
    // Un partage en cours ramène toujours sur sa ligne.
    val selected = network?.lines?.firstOrNull { it.id == (active?.lineId ?: selectedId) }
    val shownDirection = active?.directionIndex ?: directionIndex

    BackHandler(enabled = selected != null && active == null) { selectedId = null }

    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.safeDrawingPadding()) {
            TransitMap(selected, shownDirection, Modifier.fillMaxWidth().weight(1f))
            Box(Modifier.fillMaxWidth().weight(1.2f)) {
                when {
                    loading is Loading.InProgress -> CircularProgressIndicator(Modifier.align(Alignment.Center))
                    loading is Loading.Missing -> Text(
                        stringResource(R.string.network_missing),
                        Modifier.padding(24.dp),
                    )
                    selected == null -> LineList(network!!.lines) { line ->
                        selectedId = line.id
                        directionIndex = 0
                    }
                    else -> LineDetail(
                        line = selected,
                        directionIndex = shownDirection,
                        sharing = active,
                        onDirection = { directionIndex = it },
                        onBack = { selectedId = null },
                        onStop = { context.startService(ShareService.stopIntent(context)) },
                    )
                }
            }
        }
    }
}

@Composable
private fun LineList(lines: List<TransitLine>, onSelect: (TransitLine) -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    var mode by rememberSaveable { mutableStateOf<String?>(null) }
    val filtered = remember(lines, query, mode) {
        val q = query.trim().lowercase()
        lines.filter { line ->
            (mode == null || line.mode == mode) &&
                (q.isEmpty() || line.label.lowercase().contains(q) || line.longName.lowercase().contains(q))
        }
    }

    Column {
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            placeholder = { Text(stringResource(R.string.search_hint)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        )
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(horizontal = 16.dp),
        ) {
            item {
                FilterChip(mode == null, { mode = null }, label = { Text(stringResource(R.string.all_modes)) })
            }
            items(Mode.entries) { m ->
                FilterChip(mode == m.key, { mode = if (mode == m.key) null else m.key }, label = { Text(m.label) })
            }
        }
        LazyColumn(Modifier.fillMaxSize()) {
            items(filtered, key = { it.id }) { line ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth().clickable { onSelect(line) }.padding(horizontal = 16.dp, vertical = 10.dp),
                ) {
                    LineBadge(line)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(line.longName, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(
                            "${Mode.of(line.mode)?.label.orEmpty()} · ${line.operator}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                HorizontalDivider()
            }
        }
    }
}

@Composable
private fun LineDetail(
    line: TransitLine,
    directionIndex: Int,
    sharing: ShareSession.State.Active?,
    onDirection: (Int) -> Unit,
    onBack: () -> Unit,
    onStop: () -> Unit,
) {
    val context = LocalContext.current
    val direction = line.directions[directionIndex]
    var permissionDenied by remember { mutableStateOf(false) }
    val permissions = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        permissionDenied = granted[Manifest.permission.ACCESS_FINE_LOCATION] != true
        if (!permissionDenied) startSharing(context, line, directionIndex)
    }
    val now = remember { LocalTime.now() }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) {
            if (sharing == null) TextButton(onClick = onBack) { Text(stringResource(R.string.back)) }
            LineBadge(line)
            Spacer(Modifier.width(8.dp))
            Text(line.longName, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        if (sharing == null) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
                line.directions.forEachIndexed { index, d ->
                    FilterChip(
                        selected = index == directionIndex,
                        onClick = { onDirection(index) },
                        label = { Text(stringResource(R.string.direction_to, d.headsign), maxLines = 1, overflow = TextOverflow.Ellipsis) },
                        modifier = Modifier.widthIn(max = 200.dp),
                    )
                }
            }
            Button(
                onClick = { permissions.launch(requiredPermissions()) },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            ) { Text(stringResource(R.string.share_start)) }
            if (permissionDenied) {
                Text(
                    stringResource(R.string.permission_needed),
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }
        } else {
            SharingCard(sharing, onStop)
        }
        Text(
            stringResource(R.string.stops_count, direction.stops.size),
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
        LazyColumn(Modifier.fillMaxSize()) {
            items(direction.stops, key = { it.id }) { directionStop ->
                val stop = line.stop(directionStop.id) ?: return@items
                val next = line.nextDepartures(stop.id, direction.headsign, now)
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                ) {
                    Box(Modifier.size(10.dp).background(line.composeColor, CircleShape))
                    Spacer(Modifier.width(12.dp))
                    Text(stop.name, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        next.joinToString("  ") { it.format(TIME_FORMAT) },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun SharingCard(sharing: ShareSession.State.Active, onStop: () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        Column(Modifier.padding(16.dp)) {
            Text(stringResource(R.string.direction_to, sharing.headsign), fontWeight = FontWeight.SemiBold)
            Text(
                when (val status = sharing.status) {
                    ShareSession.Status.Checking -> stringResource(R.string.status_pending)
                    is ShareSession.Status.OnRoute -> stringResource(
                        R.string.status_on_route, (status.speedMps * 3.6).roundToInt(), status.alongM.roundToInt(),
                    )
                    is ShareSession.Status.Rejected -> stringResource(R.string.status_off_route, status.reason)
                },
                style = MaterialTheme.typography.bodyMedium,
            )
            OutlinedButton(onClick = onStop, modifier = Modifier.padding(top = 8.dp)) {
                Text(stringResource(R.string.share_stop))
            }
        }
    }
}

@Composable
private fun LineBadge(line: TransitLine) {
    Text(
        line.label,
        color = Color.White,
        fontWeight = FontWeight.Bold,
        maxLines = 1,
        modifier = Modifier
            .widthIn(min = 40.dp, max = 120.dp)
            .background(line.composeColor, RoundedCornerShape(50))
            .padding(horizontal = 10.dp, vertical = 4.dp),
    )
}

private val TransitLine.composeColor: Color
    get() = color?.let { runCatching { Color(android.graphics.Color.parseColor(it)) }.getOrNull() } ?: Color.DarkGray

private val TIME_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

private fun requiredPermissions(): Array<String> = buildList {
    add(Manifest.permission.ACCESS_FINE_LOCATION)
    add(Manifest.permission.ACCESS_COARSE_LOCATION)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) add(Manifest.permission.POST_NOTIFICATIONS)
}.toTypedArray()

private fun startSharing(context: Context, line: TransitLine, directionIndex: Int) {
    val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
    if (granted == PackageManager.PERMISSION_GRANTED) {
        ContextCompat.startForegroundService(context, ShareService.startIntent(context, line.id, directionIndex))
    }
}
