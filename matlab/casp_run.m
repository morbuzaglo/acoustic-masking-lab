function casp_run(jobfile, outfile, amtroot)
%CASP_RUN  Detectability of a target in maskers with the CASP model (AMT 1.6.0: paulick2024).
%
%   casp_run(jobfile, outfile, amtroot)
%
%   jobfile : .mat file written by backend/aml/casp_bridge.py with
%               fs        sampling rate (Hz), 44100 recommended
%               target    n x 1   target event, pressure in Pa at the receiver
%               maskers   n x R x M  M masker types x R independent realisations, Pa at the receiver
%               gm_db     1 x G    masker level offsets (dB) applied to every masker
%               sup_db    scalar   level (dB) added to the target for the supra-threshold template
%               model     'paulick2024' (default) or 'jepsen2008'
%               labels    cell array of M masker names
%   outfile : JSON result file
%
%   The back end follows AMT's demo_paulick2024 / Paulick et al. (2024): a template is built from the
%   (supra-threshold target + masker) minus (masker) internal representation, a region of interest of
%   auditory channels is chosen from the adaptation-stage output, each stimulus interval is correlated
%   with the template after subtracting the mean masker representation, and PAULICK2024_DECISION maps the
%   correlation to P(correct) of a 2AFC trial. NOTHING in this file replaces a CASP stage with a
%   simpler algorithm.
    t_start = tic;
    logf = [outfile '.progress'];
    wlog = @(s) local_log(logf, s);
    addpath(genpath(amtroot));
    amt_start('silent');
    J = load(jobfile);
    fs = double(J.fs);
    target = double(J.target(:));
    maskers = double(J.maskers);
    if ndims(maskers) == 2, maskers = reshape(maskers, size(maskers,1), size(maskers,2), 1); end
    [n, R, M] = size(maskers);
    gm = double(J.gm_db(:))';
    G = numel(gm);
    sup_db = double(J.sup_db);
    if isfield(J, 'model') && ~isempty(J.model), model = char(J.model); else, model = 'paulick2024'; end
    labels = J.labels;
    if ischar(labels), labels = {labels}; end
    nAFC = 2; rule = [1 2];

    P = nan(M, G); MU = nan(M, G); PSTD = nan(M, G); MUR = nan(M, G, R);
    rep_map = struct('fc', [], 'time', [], 'data', []);
    total = M * G * R * 3; done = 0;
    for m = 1:M
        for g = 1:G
            gain = 10^(gm(g)/20);
            tsup = target * 10^(sup_db/20);
            reps_m = cell(R,1); reps_s = cell(R,1); reps_t = cell(R,1);
            adap_m = cell(R,1); adap_s = cell(R,1);
            for r = 1:R
                mk = maskers(:, r, m) * gain;
                [reps_m{r}, Ym, fc_aud, fc_mod, fsR] = paulick2024(mk, fs, 'model', model);
                adap_m{r} = Ym.adaptation; done = done + 1;
                [reps_s{r}, Ys] = paulick2024(mk + tsup, fs, 'model', model);
                adap_s{r} = Ys.adaptation; done = done + 1;
                [reps_t{r}, Yt] = paulick2024(mk + target, fs, 'model', model);
                done = done + 1;
                if r == 1 && g == ceil(G/2) && m == 1
                    A = Yt.adaptation; step = max(1, floor(size(A,1)/160));
                    rep_map.fc = fc_aud(:)'; rep_map.time = ((1:step:size(A,1)) - 1) / fs;
                    rep_map.data = A(1:step:end, :);
                end
                wlog(sprintf('%d %d %.1f', done, total, toc(t_start)));
            end
            refsum = zeros(size(reps_m{1})); adap_diff = zeros(size(adap_m{1}));
            for r = 1:R
                refsum = refsum + reps_m{r};
                adap_diff = adap_diff + (adap_s{r} - adap_m{r}) / R;
            end
            roi = paulick2024_roi(adap_diff, fs, fc_aud);
            template = zeros(size(refsum));
            for r = 1:R, template = template + (reps_s{r} - reps_m{r}) / R; end  % noise-realisation specific parts average out
            c = sqrt(fsR / sum(template.^2, 'all', 'omitnan'));
            template = c * template;
            probs = nan(R,1); mus = nan(R,1);
            for r = 1:R
                rr = mod(r, R) + 1;                          % a different masker realisation for the mask-only interval
                % leave-one-out reference: the mean masker representation never contains the interval under test
                it = reps_t{r} - (refsum - reps_m{r}) / (R - 1);
                im = reps_m{rr} - (refsum - reps_m{rr}) / (R - 1);
                ct = paulick2024_corr(it(:, roi.idx, :), template(:, roi.idx, :), fs, roi.freq, fc_mod);
                cm = paulick2024_corr(im(:, roi.idx, :), template(:, roi.idx, :), fs, roi.freq, fc_mod);
                mu = 1/fsR * max(0, ct.fin - max(0, cm.fin));
                [~, pr] = paulick2024_decision(mu, nAFC, rule, 'model', model);
                probs(r) = pr; mus(r) = mu;
            end
            P(m, g) = mean(probs); PSTD(m, g) = std(probs); MU(m, g) = mean(mus); MUR(m, g, :) = mus;
        end
    end
    out = struct('model', model, 'labels', {labels}, 'gm_db', gm, 'P2AFC', P, 'P_std', PSTD, 'mu', MU, 'mu_r', MUR, 'in_var_default', 40, ...
                 'fs', fs, 'n_samples', n, 'n_realisations', R, 'sup_db', sup_db, ...
                 'rep_map', rep_map, 'elapsed_s', toc(t_start), 'amt_version', '1.6.0');
    fid = fopen(outfile, 'w'); fwrite(fid, jsonencode(out), 'char'); fclose(fid);
    wlog('DONE');
end

function local_log(f, s)
    fid = fopen(f, 'a'); if fid > 0, fprintf(fid, '%s\n', s); fclose(fid); end
end
