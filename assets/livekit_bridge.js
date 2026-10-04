/*
 * Browser half of the Reflex <-> LiveKit bridge.
 *
 * LiveKitBridgeState drives this object with rx.call_script(...):
 *   window.livekitClient.connect(url, token, bridgeInputId)
 *   window.livekitClient.setMicrophone(enabled)
 *   window.livekitClient.startAudio()
 *   window.livekitClient.disconnect()
 * and receives room updates as JSON through a hidden <input> whose onChange
 * is bound to LiveKitBridgeState.handle_js_message.
 *
 * Needs /livekit-client.umd.js (vendored livekit-client, global LivekitClient).
 */
(function () {
  if (window.livekitClient) return;

  // The SDK disconnects by itself when the page goes away (reload, close);
  // that is not a dropped connection, so don't report it to the backend.
  let leaving = false;
  window.addEventListener('beforeunload', () => { leaving = true; });
  window.addEventListener('pagehide', () => { leaving = true; });

  // The backend hands us its own URL (ws://localhost:8000 locally,
  // wss://<sub>.reflex-ddns.com behind re-ddns); the SDK appends /rtc.
  function signalUrl(url) {
    const u = new URL(url, window.location.href);
    if (u.protocol === 'http:') u.protocol = 'ws:';
    if (u.protocol === 'https:') u.protocol = 'wss:';
    if (window.location.protocol === 'https:' && u.protocol === 'ws:') u.protocol = 'wss:';
    return u.toString().replace(/\/$/, '');
  }

  function initials(name) {
    const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : (parts[0] || '?').slice(0, 2);
    return letters.toUpperCase();
  }

  function avatarColor(seed) {
    let hue = 0;
    for (const ch of String(seed)) hue = (hue * 31 + ch.codePointAt(0)) % 360;
    return 'hsl(' + hue + ' 65% 50%)';
  }

  function audioHolder() {
    let holder = document.getElementById('livekit-audio-holder');
    if (!holder) {
      holder = document.createElement('div');
      holder.id = 'livekit-audio-holder';
      holder.style.display = 'none';
      document.body.appendChild(holder);
    }
    return holder;
  }

  window.livekitClient = {
    room: null,
    audioInterval: null,
    bridgeInputId: null,

    async connect(url, token, bridgeInputId) {
      this.bridgeInputId = bridgeInputId;
      const LK = window.LivekitClient;
      if (!LK) {
        this.sendStatus({ type: 'error', message: 'livekit-client.umd.js failed to load' });
        return;
      }
      if (this.room) await this.disconnect();

      const room = new LK.Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        publishDefaults: { audioPreset: LK.AudioPresets.music },
      });
      this.room = room;
      const E = LK.RoomEvent;
      const refresh = () => this.updateParticipants();

      room
        .on(E.Connected, () => this.sendStatus({ status: 'Connected' }))
        .on(E.Reconnecting, () => this.sendStatus({ status: 'Reconnecting...' }))
        .on(E.Reconnected, () => this.sendStatus({ status: 'Connected' }))
        .on(E.ParticipantConnected, refresh)
        .on(E.ParticipantDisconnected, refresh)
        .on(E.ActiveSpeakersChanged, refresh)
        .on(E.TrackMuted, refresh)
        .on(E.TrackUnmuted, refresh)
        .on(E.LocalTrackPublished, refresh)
        .on(E.TrackSubscribed, (track) => {
          // Keep remote audio elements in the DOM (as LiveKit's own demo does).
          if (track.kind === 'audio') audioHolder().appendChild(track.attach());
          refresh();
        })
        .on(E.TrackUnsubscribed, (track) => {
          track.detach().forEach((el) => el.remove());
          refresh();
        })
        .on(E.AudioPlaybackStatusChanged, () => {
          this.sendStatus({ audio_blocked: !room.canPlaybackAudio });
        })
        .on(E.MediaDevicesError, (e) => {
          this.sendStatus({ type: 'warning', message: 'Microphone error: ' + e.message });
        })
        .on(E.Disconnected, () => {
          // Ignore the event caused by our own disconnect() (leave / rejoin).
          if (this.room !== room || leaving) return;
          this.room = null;
          this.stopAudioVisualizer();
          this.sendStatus({ status: 'Disconnected', participants: [] });
        });

      try {
        await room.connect(signalUrl(url), token);
      } catch (error) {
        console.error('LiveKit connection error:', error);
        if (this.room === room) this.room = null;
        this.sendStatus({ type: 'error', message: error.message || String(error) });
        return;
      }

      try {
        await room.localParticipant.setMicrophoneEnabled(true);
      } catch (error) {
        // Stay in the room as a listener (no mic, or permission denied).
        this.sendStatus({ type: 'warning', message: 'Joined without microphone: ' + (error.message || error) });
      }

      this.updateParticipants();
      this.startAudioVisualizer();
      this.sendStatus({ status: 'Connected', audio_blocked: !room.canPlaybackAudio });
    },

    async disconnect() {
      const room = this.room;
      this.room = null;
      this.stopAudioVisualizer();
      if (room) await room.disconnect();
      audioHolder().replaceChildren();
    },

    async setMicrophone(enabled) {
      if (!this.room) return;
      try {
        await this.room.localParticipant.setMicrophoneEnabled(enabled);
      } catch (error) {
        this.sendStatus({ type: 'warning', message: 'Microphone error: ' + (error.message || error) });
      }
      this.updateParticipants();
    },

    async startAudio() {
      if (!this.room) return;
      await this.room.startAudio();
      this.sendStatus({ audio_blocked: !this.room.canPlaybackAudio });
    },

    startAudioVisualizer() {
      this.stopAudioVisualizer();
      this.audioInterval = setInterval(() => {
        if (!this.room) return;
        const updateBar = (p) => {
          const el = document.getElementById('vol-' + p.identity);
          if (!el) return;
          const level = p.audioLevel || 0;
          let width = Math.min(100, level * 100 * 5);
          if (width > 0 && width < 5) width = 5;
          el.style.width = width + '%';
        };
        updateBar(this.room.localParticipant);
        this.room.remoteParticipants.forEach(updateBar);
      }, 50);
    },

    stopAudioVisualizer() {
      if (this.audioInterval) {
        clearInterval(this.audioInterval);
        this.audioInterval = null;
      }
    },

    updateParticipants() {
      const room = this.room;
      if (!room) return;
      const describe = (p, isLocal) => {
        const name = p.name || p.identity;
        return {
          identity: p.identity,
          name: name,
          initials: initials(name),
          avatar_color: avatarColor(name),
          is_speaking: p.isSpeaking,
          is_local: isLocal,
          is_muted: !p.isMicrophoneEnabled,
        };
      };
      const participants = [describe(room.localParticipant, true)];
      room.remoteParticipants.forEach((p) => participants.push(describe(p, false)));
      this.sendStatus({
        participants: participants,
        is_muted: !room.localParticipant.isMicrophoneEnabled,
      });
    },

    sendStatus(data) {
      const input = document.getElementById(this.bridgeInputId);
      if (!input) return;
      // React ignores plain value assignments; use the native setter + input event.
      const setValue = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setValue.call(input, JSON.stringify(data));
      input.dispatchEvent(new Event('input', { bubbles: true }));
    },
  };
})();
