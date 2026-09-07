import React from 'react';
import styles from './AccidentSection.module.scss';

export const AccidentSection: React.FC = () => {
  return (
    <section id="accidents" className={styles.section}>
      <div className={styles.textCol}>
        <span className={styles.eyebrow}>THE PROBLEM</span>
        <h2>Underwater accidents happen without warning</h2>
        <p>
          Submerged wreckage, entangled trawl nets, and unmarked debris are among the
          leading causes of underwater equipment damage and diver-safety incidents.
          Traditional sonar sweeps often miss low-contrast hazards until it's too late.
        </p>
        <p>
          AquaTrace's acoustic shadow analysis pipeline is built specifically to catch
          these risks early — surfacing verified hazard targets with confidence scores,
          dimensions, and exact GPS coordinates, so crews can reroute before an incident
          occurs instead of reacting after one.
        </p>
      </div>
      <div className={styles.imageCol}>
        <img src="/accident.jpg" alt="Underwater accident hazard" />
      </div>
    </section>
  );
};

export default AccidentSection;