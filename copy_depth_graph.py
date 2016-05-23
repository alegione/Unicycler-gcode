from __future__ import print_function
from __future__ import division
from assembly_graph import AssemblyGraph

class CopyDepthGraph(AssemblyGraph):
    '''
    This class add copy depth tracking to the basic assembly graph.
    '''
    def __init__(self, filename, overlap, error_margin):
        '''
        The only argument in addition to those used in AssemblyGraph is error_margin.  This
        specifies the allowed relative depth used when making copy depth assignments.  For example,
        if error_margin = 0.2, then 20% error is acceptable.
        '''
        AssemblyGraph.__init__(self, filename, overlap)
        self.copy_depths = {} # Dictionary of segment number -> list of copy depths
        self.error_margin = error_margin
        self.minimum_auto_single = self.get_n_segment_length(95)


    def save_to_gfa(self, filename):
        gfa = open(filename, 'w')
        sorted_segments = sorted(self.segments.values(), key=lambda x: x.number)
        for segment in sorted_segments:
            segment_line = segment.gfa_segment_line()
            segment_line = segment_line[:-1] # Remove newline
            if segment.number in self.copy_depths:
                segment_line += '\tLB:z:' + self.get_depth_string(segment)
                segment_line += '\tCL:z:' + self.get_copy_number_colour(segment)
            segment_line += '\n'
            gfa.write(segment_line)
        gfa.write(self.get_all_gfa_link_lines())

    def get_depth_string(self, segment):
        '''
        Given a particular segment, this function returns a string with the segment's copy depths
        (if it has any).
        '''
        if segment.number not in self.copy_depths:
            return ''
        return ', '.join(['%.3f' % x for x in self.copy_depths[segment.number]])

    def get_copy_number_colour(self, segment):
        '''
        Given a particular segment, this function returns a colour string based on the copy number.
        '''
        if segment.number not in self.copy_depths:
            return 'black'
        copy_number = len(self.copy_depths[segment.number])
        if copy_number == 1:
            return 'forestgreen'
        if copy_number == 2:
            return 'gold'
        if copy_number == 3:
            return 'darkorange'
        else: # 4+
            return 'red'

    # def determine_copy_depth(self):

    #     one_link_segments = [x for x in self.segments.values() if self.at_most_one_link_per_end(x)]

    #     for seg in one_link_segments:
    #         depth = seg.depth

    #     base_depths = []
    #     for seg in one_link_segments:
    #         base_depths += [seg.depth] * seg.get_length()
    #     base_depths = sorted(base_depths)
    #     median_depth = get_median(base_depths)
    #     absolute_deviations = [abs(x - median_depth) for x in base_depths]
    #     median_absolute_deviation = 1.4826 * get_median(sorted(absolute_deviations))

    #     print('median_depth', median_depth)
    #     print('median_absolute_deviation', median_absolute_deviation)

    #     for seg in one_link_segments:
    #         depth = seg.depth
    #         robust_z_score = (seg.depth - median_depth) / median_absolute_deviation
    #         print(seg.number, seg.depth, robust_z_score)


    #     # depth_file = open('/Users/Ryan/Desktop/depths.txt', 'w')
    #     # for depth in base_depths:
    #     #     depth_file.write(str(depth) + '\n')
    #     # depth_file.close()







    def determine_copy_depth(self):
        '''
        This function iteratively applies the various methods for assigning copy depth to segments
        until no more assignments can be made.  It may not succeed in assigning copy depths to all
        segments, as some segments will have strange/difficult connections or depth which prevent
        automatic copy depth determination.
        '''
        while self.assign_single_copy_depth():
            self.determine_copy_depth_part_2()

    def determine_copy_depth_part_2(self):
        while self.merge_copy_depths():
            pass
        if self.redistribute_copy_depths():
            self.determine_copy_depth_part_2()
        while self.simple_loop_copy_depths():
            pass

    def assign_single_copy_depth(self):
        '''
        This function assigns a single copy to the longest segment with no more than one link per
        end.
        '''
        segments = sorted(self.get_segments_without_copies(), key=lambda x: x.get_length(), reverse=True)
        for segment in segments:
            if segment.get_length() >= self.minimum_auto_single and \
               self.at_most_one_link_per_end(segment):
                self.copy_depths[segment.number] = [segment.depth]
                print('assign_single_copy_segments:', segment.number) # TEMP
                return 1
        print('assign_single_copy_segments: ') # TEMP
        return 0

    def merge_copy_depths(self):
        '''
        This function looks for segments where they have input on one end where:
          1) All input segments have copy depth assigned.
          2) All input segments exclusively input to this segment.
        All such cases are evaluated, and the segment with the lowest error (if that error is below
        the allowed error margin) is assigned copy depths, scaling the inputs so their sum
        exactly matches the segment's depth.
        '''
        segments = self.get_segments_without_copies()
        if not segments:
            print('merge_copy_depths:           ') # TEMP
            return 0
        
        best_segment_num = None
        best_new_depths = []
        lowest_error = float('inf')

        for segment in segments:
            num = segment.number
            exclusive_inputs = self.get_exclusive_inputs(num)
            exclusive_outputs = self.get_exclusive_outputs(num)
            in_depth_possible = exclusive_inputs and self.all_have_copy_depths(exclusive_inputs)
            out_depth_possible = exclusive_outputs and self.all_have_copy_depths(exclusive_outputs)
            if in_depth_possible:
                depths, error = self.scale_copy_depths_from_source_segments(num, exclusive_inputs)
                if error < lowest_error:
                    lowest_error = error
                    best_segment_num = num
                    best_new_depths = depths
            if out_depth_possible:
                depths, error = self.scale_copy_depths_from_source_segments(num, exclusive_outputs)
                if error < lowest_error:
                    lowest_error = error
                    best_segment_num = num
                    best_new_depths = depths
        if best_segment_num and lowest_error < self.error_margin:
            print('merge_copy_depths:          ', best_segment_num) # TEMP
            self.copy_depths[best_segment_num] = best_new_depths
            return 1
        else:
            print('merge_copy_depths:           ') # TEMP
            return 0

    def redistribute_copy_depths(self):
        '''
        This function deals with the easier case of copy depth redistribution: where one segments
        with copy depth leads exclusively to multiple segments without copy depth.
        We will then try to redistribute the source segment's copy depths among the destination
        segments.  If it can be done within the allowed error margin, the destination segments will
        get their copy depths.
        '''
        segments = self.get_segments_with_two_or_more_copies()
        if not segments:
            print('redistribute_copy_depths:    ') # TEMP
            return 0
        assignment_count = 0
        for segment in segments:
            num = segment.number
            connections = self.get_exclusive_inputs(num)
            if not connections or self.all_have_copy_depths(connections):
                connections = self.get_exclusive_outputs(num)
            if not connections or self.all_have_copy_depths(connections):
                continue

            # If we got here, then we can try to redistribute the segment's copy depths to its
            # connections which are lacking copy depth.
            copy_depths = self.copy_depths[num]
            bins = [[]] * len(connections)
            targets = [None if x not in self.copy_depths else len(self.copy_depths[x]) for x in connections]
            arrangments = shuffle_into_bins(copy_depths, bins, targets)
            if not arrangments:
                continue

            lowest_error = float('inf')
            for arrangment in arrangments:
                error = self.get_error_for_multiple_segments_and_depths(connections, arrangment)
                if error < lowest_error:
                    lowest_error = error
                    best_arrangement = arrangment
            if lowest_error < self.error_margin:
                if self.assign_copy_depths_where_needed(connections, best_arrangement):
                    print('redistribute_copy_depths:   ', num) # TEMP
                    return 1

        print('redistribute_copy_depths:    ') # TEMP
        return 0

    def simple_loop_copy_depths(self):
        '''
        This function assigns copy depths to simple loop structures.  It will only assign copy
        depths in cases where the loop occurs once - higher repetition loops will not be given copy
        depths due to the increasing uncertainty in repetition counts.
        '''
        assignment_count = 0
        # TO DO
        # TO DO
        # TO DO
        # TO DO
        # TO DO
        # TO DO
        print('simple_loop_copy_depths:     ') # TEMP
        return assignment_count
        
    def at_most_one_link_per_end(self, segment):
        '''
        Returns True if the given segment has no more than one link on either end.
        '''
        num = segment.number
        if num in self.forward_links and len(self.forward_links[num]) > 1:
            return False
        if num in self.reverse_links and len(self.reverse_links[num]) > 1:
            return False
        return True

    def all_have_copy_depths(self, segment_numbers):
        '''
        Takes a list of segment numbers and returns whether every segment in the list has copy
        depths assigned.
        '''
        for num in segment_numbers:
            if num not in self.copy_depths:
                return False
        return True

    def scale_copy_depths_from_source_segments(self, segment_number, source_segment_numbers):
        '''
        Using a list of segments which are the source of copy depth, this function scales them so
        that their sum matches the depth of the given segment.
        It returns:
          1) a list of depth numbers
          2) the error (i.e. the degree of scaling which had to occur)
        It assumes that all of the source segments definitely have copy depths.
        '''
        source_depths = []
        for num in source_segment_numbers:
            source_depths += self.copy_depths[num]
        target_depth = self.segments[segment_number].depth
        return self.scale_copy_depths(target_depth, source_depths)

    def scale_copy_depths(self, target_depth, source_depths):
        '''
        This function takes the source depths and scales them so their sum matches the target
        depth.  It returns the scaled depths and the error.
        '''
        source_depth_sum = sum(source_depths)
        scaling_factor = target_depth / source_depth_sum
        scaled_depths = sorted([scaling_factor * x for x in source_depths], reverse=True)
        error = get_error(source_depth_sum, target_depth)
        return scaled_depths, error

    def get_segments_without_copies(self):
        '''
        Returns a list of the graph segments lacking copy depth information.
        '''
        return [x for x in self.segments.values() if x.number not in self.copy_depths]

    def get_segments_with_two_or_more_copies(self):
        return [x for x in self.segments.values() if x.number in self.copy_depths and len(self.copy_depths[x.number]) > 1]

    def get_error_for_multiple_segments_and_depths(self, segment_numbers, copy_depths):
        '''
        For the given segments, this function assesses how well the given copy depths match up.
        The maximum error for any segment is what's returned at the end.
        '''
        max_error = 0
        for i, num in enumerate(segment_numbers):
            segment_depth = self.segments[num].depth
            depth_sum = sum(copy_depths[i])
            max_error = max(max_error, get_error(depth_sum, segment_depth))
        return max_error

    def assign_copy_depths_where_needed(self, segment_numbers, new_depths):
        '''
        For the given segments, this function assigns the corresponding copy depths, scaled to fit
        the segment.  If a segment already has copy depths, it is skipped (i.e. this function only
        write new copy depths, doesn't overwrite existing ones).
        It will only create copy depths if doing so is within the allowed error margin.
        '''
        success = False
        for i, num in enumerate(segment_numbers):
            if num not in self.copy_depths:
                new_copy_depths, error = self.scale_copy_depths(self.segments[num].depth, new_depths[i])
                if error <= self.error_margin:
                    self.copy_depths[num] = new_copy_depths
                    success = True
        return success









def get_error(source, target):
    '''
    Returns the relative error from trying to assign the source value to the target value.
    E.g. if source = 1.6 and target = 2.0, the error is 0.2
    '''
    if target > 0.0:
        return abs(source - target) / target
    else:
        return float('inf')

def within_error_margin(val_1, val_2, error_margin):
    '''
    Returns whether val_1 is within the error margin of val_2.
    I.e. val_2 * (1 - em) <= val_1 <= val_2 * (1 + em)
    E.g. if val_2 is 100 and the error margin is 0.3, then val_1 must be in the range of 70 to 130
         (inclusive) for this function to return true.
    '''
    return val_1 >= val_2 * (1 - error_margin) and val_1 <= val_2 * (1 + error_margin)

def shuffle_into_bins(items, bins, targets):
    '''
    Shuffle items into bins in all possible arrangements that satisfy these conditions:
      1) All bins must have at least one item.
      2) Any bins with a specified target must have exactly that number of items.
    '''
    arrangements = []

    # If there are items not yet in a bin, place the first item in each possible bin and call this
    # function recursively.
    if items:
        for i, _ in enumerate(bins):
            bins_copy = [list(x) for x in bins]
            bins_copy[i].append(items[0])
            arrangements += shuffle_into_bins(items[1:], bins_copy, targets)

    # If all items are in a bin, all bins have at least one item and any bins with a target have
    # the appropriate amount, then add the arrangement to the results.
    elif all(x for x in bins) and \
         all([not target or target == len(bins[i]) for i, target in enumerate(targets)]):
            arrangements.append(bins)

    return arrangements

def get_median(sorted_list):
    count = len(sorted_list)
    index = (count - 1) // 2
    if (count % 2):
        return sorted_list[index]
    else:
        return (sorted_list[index] + sorted_list[index + 1]) / 2.0
