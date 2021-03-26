from .models import *
import pandas as pd

#-------------------------------------------------------------
# Masking


def find_nested_events(samples, outer, inner):
    """ Returns indices of events in outer that contain events in inner

    This is helpful for dealing with EyeLink blink events. Each is embedded
    within a saccade event, and the EyeLink documentation states that data
    within saccades that contain blinks is unreliable. So we use this method
    to find those saccade events.

    Parameters
    ----------
    samples (cili Samples)
        The samples object to which the events objects refer.
    outer (cili Events)
        The list of events you'd like to search for ones containing events in
        'inner.'
    inner (cili Events)
        The list of events whose containing events from 'outer' you're trying
        to find.
    """
    # looking for inner events whose onset is at or before outer offset,
    # and whose offset is at or after inner onset.
    # get list of onsets of first samples *after* inner events
    onsets = inner.index.to_series()
    post_onsets = onsets + inner.duration
    # convert to list of positional indices
    max_onset = samples.index[-1]
    last_idxs = post_onsets.apply(lambda x: max(
        0, samples.index.searchsorted(x, side="right") - 1))
    # step back by one positional index to get pos. index of last samples of our events.
    # stupid fix - don't nudge the index back for events whose duration went beyond the samples
    end_safe_evs = post_onsets <= max_onset
    last_idxs[end_safe_evs] = last_idxs[end_safe_evs] - 1
    # get the time indices of the last samples of our events
    last_onsets = last_idxs.apply(lambda x: samples.index[x])
    idxs = outer.apply(has_overlapping_events, axis=1,
                       args=[onsets, last_onsets])
    if len(idxs) == 0:
        return pd.DataFrame()
    return outer[idxs]


def has_overlapping_events(event, onsets, last_onsets):
    """ Searches for onset/last_onset pairs overlapping with the event in 'event.'

    Specifically, searches series last_onsets for rows with onset <= event
    offset, and offset >= event onset.

    Parameters
    ----------
    event (1xN DataFrame)
        The event you're testing for intersection with the onsets/last_onsets.
    onsets (numpy array like)
        Onset indices of potentially intersecting events.
    last_onsets (numpy array like)
        Last indices of the potentially intersecting events.
    """
    matches = last_onsets[(onsets <= event.name +
                           event.duration) & (last_onsets >= event.name)]
    return len(matches) > 0


def get_eyelink_mask_events(samples, events, find_recovery=True):
    """ Finds events from EyeLink data that contain untrustworthy data.

    Per the EyeLink documentation, we return EBLINK events as well as any
    saccade containing a blink event. We also use adjust_eyelink_recov_idxs to
    push the end of these events slightly farther forward than the EyeLink-
    reported endpoints, because they often include data that is clearly bad.

    Parameters
    ----------
    samples (cili Samples)
        The samples in which the events in 'events' occur.
    events (cili Events)
        The events you'd like to search for blinks and bad saccades.
    find_recovery (bool)
        Defaul True. If true, we will use adjust_eyelink_recov_idxs to find
        the proper ends for blink events.
    """
    be = events.EBLINK.duration.to_frame()
    be = pd.concat([be, find_nested_events(
        samples, events.ESACC.duration.to_frame(), be)])
    if find_recovery:
        adjust_eyelink_recov_idxs(samples, be)
    return be


def get_eyelink_mask_idxs(samples, events, find_recovery=True):
    """ Calls get_eyelink_mask_events, finds indices from 'samples' within the returned events.

    See notes on get_eyelink_mask_events FMI.
    """
    be = get_eyelink_mask_events(samples, events, find_recovery=find_recovery)
    bi = ev_row_idxs(samples, be)
    return bi


def mask_eyelink_blinks(samples, events, mask_fields=["pup_l"], find_recovery=True):
    """ Sets the value of all untrustworthy data points to NaN.

    Per the EyeLink documentation, we include blink events as well as any
    saccade containing a blink event. We also use adjust_eyelink_recov_idxs to
    push the end of these events slightly farther forward than the EyeLink-
    reported endpoints, because they often include data that is clearly bad.

    Parameters
    ----------
    samples (cili Samples)
        The samples in which the events in 'events' occur.
    events (cili Events)
        The events you'd like to search for blinks and bad saccades.
    mask_fields (list of strings)
        The columns you'd like set to NaN for bad event indices.
    find_recovery (bool)
        Defaul True. If true, we will use adjust_eyelink_recov_idxs to find
        the proper ends for blink events.
    """
    samps = samples.copy(deep=True)
    indices = get_eyelink_mask_idxs(samps, events, find_recovery=find_recovery)
    samps.loc[indices, mask_fields] = float('nan')
    return samps


def mask_zeros(samples, mask_fields=["pup_l"]):
    """ Sets any 0 values in columns in mask_fields to NaN

    Parameters
    ----------
    samples (cili Samples)
        The samples you'd like to search for 0 values.
    mask_fields (list of strings)
        The columns in you'd like to search for 0 values.
    """
    samps = samples.copy(deep=True)
    for f in mask_fields:
        samps[samps[f] == 0] = float("nan")
    return samps


def interp_zeros(samples, interp_fields=["pup_l"]):
    """ Replace 0s in 'samples' with linearly interpolated data.

    Parameters
    ----------
    samples (cili Samples)
        The samples in which you'd like to replace 0s
    interp_fields (list of strings)
        The column names from samples in which you'd like to replace 0s.
    """
    samps = mask_zeros(samples, mask_fields=interp_fields)
    samps = samps.interpolate(method="linear", axis=0, inplace=False)
    # since interpolate doesn't handle the start/finish, bfill the ffill to
    # take care of NaN's at the start/finish samps.
    samps.fillna(method="bfill", inplace=True)
    samps.fillna(method="ffill", inplace=True)
    return samps


def interp_eyelink_blinks(samples, events, find_recovery=True, interp_fields=["pup_l"]):
    """ Replaces the value of all untrustworthy data points linearly interpolated data.

    Per the EyeLink documentation, we include blink events as well as any
    saccade containing a blink event. We also use adjust_eyelink_recov_idxs to
    push the end of these events slightly farther forward than the EyeLink-
    reported endpoints, because they often include data that is clearly bad.

    Parameters
    ----------
    samples (cili Samples)
        The samples in which the events in 'events' occur.
    events (cili Events)
        The events you'd like to search for blinks and bad saccades.
    find_recovery (bool)
        Defaul True. If true, we will use adjust_eyelink_recov_idxs to find
        the proper ends for blink events.
    interp_fields (list of strings)
        The columns in which we should interpolate data.
    """
    samps = mask_eyelink_blinks(
        samples, events, mask_fields=interp_fields, find_recovery=find_recovery)
    # inplace=True causes a crash, so for now...
    # fixed by #6284 ; will be in 0.14 release of pandas
    samps = samps.interpolate(method="linear", axis=0, inplace=True)
    return samps


def ev_row_idxs(samples, events):
    """ Returns the indices in 'samples' contained in events from 'events.'

    Parameters
    ----------
    samples (cili Samples)
        The samples you'd like to pull indices from.
    events (cili Events)
        The events whose indices you'd like to pull from 'samples.'
    """
    import numpy as np
    idxs = []
    for idx, dur in list(events.duration.items()):
        idxs.extend(list(range(idx, int(idx + dur))))
    idxs = np.unique(idxs)
    idxs = np.intersect1d(idxs, samples.index.tolist())
    return idxs


def adjust_eyelink_recov_idxs(samples, events, z_thresh=.1, window=1000, kernel_size=100):
    """ Extends event endpoint until the z-scored derivative of 'field's timecourse drops below thresh

    We will try to extend *every* event passed in.

    Parameters
    ----------
    samples (list of dicts)
        A Samples object
    events (list of dicts)
        An Events object
    z_thresh (float)
        The threshold below which the z-score of the timecourse's gradient
        must fall before we'll consider the event over.
    field (string)
        The field to use.
    window (int)
        The number of indices you'll search through for z-threshold
    kernel_size (int)
        The number of indices we'll average together at each measurement. So
        what you really get with this method is the index of the first voxel
        whose gradient value, when averaged together with that of the
        n='kernel' indices after it, then z-scored, is below the given z
        threshold.
    """
    import numpy as np
    from .util import PUP_FIELDS
    # find a pupil size field to use
    p_fields = [f for f in samples.columns if f in PUP_FIELDS]
    if len(p_fields) == 0:
        return  # if we can't find a pupil field, we won't make any adjustments
    field = p_fields[0]
    # use pandas to take rolling mean. pandas' kernel looks backwards, so we need to pull a reverse...
    dfs = np.gradient(samples[field].values)
    reversed_dfs = dfs[::-1]
    reversed_dfs_ravg = np.array(pd.Series(reversed_dfs).rolling(window=kernel_size).mean())
    dfs_ravg = reversed_dfs_ravg[::-1]
    dfs_ravg = np.abs((dfs_ravg - np.mean(dfs_ravg)) / np.std(dfs_ravg))
    samp_count = len(samples)
    # search for drop beneath z_thresh after end index
    new_durs = []
    for idx, dur in list(events.duration.items()):
        try:
            s_pos = samples.index.get_loc(idx + dur) - 1
            e_pos = samples.index[min(s_pos + window, samp_count - 1)]
        except Exception as e:
            # can't do much about that
            s_pos = e_pos = 0
        if s_pos == e_pos:
            new_durs.append(dur)
            continue
        e_dpos = np.argmax(dfs_ravg[s_pos:e_pos] < z_thresh)  # 0 if not found
        new_end = samples.index[min(s_pos + e_dpos, samp_count - 1)]
        new_durs.append(new_end - idx)
    events.duration = new_durs

#-------------------------------------------------------------
# Filters


def butterworth_series(samples, fields=["pup_l"], filt_order=5, cutoff_freq=.01, inplace=False):
    """ Applies a butterworth filter to the given fields

    See documentation on scipy's butter method FMI.
    """
    # TODO: This is pretty limited right now - you'll have to tune filt_order
    # and cutoff_freq manually. In the future, it would be nice to use
    # signal.buttord (heh) to let people adjust in terms of dB loss and
    # attenuation.
    import scipy.signal as signal
    from numpy import array
    samps = samples if inplace else samples.copy(deep=True)
    B, A = signal.butter(filt_order, cutoff_freq, output="BA")
    samps[fields] = samps[fields].apply(
        lambda x: signal.filtfilt(B, A, x), axis=0)
    return samps
